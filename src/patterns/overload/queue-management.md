# Queue Management

> **One-liner:** An unbounded FIFO queue under overload is a latency commitment you haven't made explicit — it delays failure signal, burns capacity on stale work, and prevents recovery.

## Symptom

- p99 rising over minutes or hours without a corresponding load increase (queue filling gradually).
- Memory growing steadily on the service host (queue accumulation).
- "CPU low, service slow" — threads or workers blocked waiting on queue drain rather than doing work.
- Latency spikes that clear slowly after load drops (queue draining phase).
- Items completing long after their client deadline — traces show requests that started 10 seconds ago being served now.
- After an overload event, latency remains elevated for minutes even though CPU has dropped.

## Mechanism

An unbounded FIFO queue under overload accumulates work faster than it drains. Each new arrival is placed behind all existing items. At steady-state overload (arrival rate > drain rate), the queue grows without bound. The sojourn time of the Nth item is approximately N / drain_rate — a queue of 1000 items at 100 items/second means a 10-second wait before service even begins.

The FIFO property makes this worse: the oldest items (at the head) are served first. The oldest items are also the ones most likely to have exceeded their client deadline. The server drains dead work off the front of the queue while live items accumulate at the back.

**CoDel (Controlled Delay)** targets sojourn time rather than queue length. An item is dropped or rejected when its time in the queue exceeds a target (e.g., 5ms) for a sustained interval. This keeps latency bounded regardless of queue length, at the cost of dropping some requests during overload. The key insight is that sojourn time is what callers care about, not queue length.

**Adaptive LIFO** serves the *newest* items first under overload. Newer items are more likely to have deadline remaining. By serving them first, the server maximizes the fraction of its output that reaches a live client. Older items (whose clients have timed out) naturally fall to the bottom and eventually expire without being processed. LIFO also provides backpressure signal: producers pushing to the back of the queue find the queue growing, while the server drains from the front — in LIFO, they find their items being served immediately if load is low, or dropped if load is extreme.

**Bounded FIFO** simply caps queue depth. When the cap is reached, new arrivals are rejected. This prevents memory exhaustion and ensures that the maximum sojourn time is bounded by (cap / drain_rate). The problem: at the cap, the queue is full of the oldest, most likely dead items. New arrivals are rejected while dead work is served.

The three policies differ in what they optimize:

| Policy | What it preserves | Failure mode |
|--------|-------------------|--------------|
| Unbounded FIFO | No rejections | Unbounded latency; memory exhaustion |
| Bounded FIFO | Maximum queue depth | Rejects live work; serves dead work |
| Adaptive LIFO | Deadline-likely requests | Starvation of old requests |
| CoDel | Sojourn time bound | Drops requests during transients |

## Real-world sightings

**Nichols and Jacobson, "Controlling Queue Delay" (CACM 2012).** CoDel was developed to address bufferbloat — the phenomenon where large buffers in network equipment hold so much queued data that packets experience hundreds of milliseconds of sojourn time. The paper shows that queue length is a lagging indicator; sojourn time is what matters, and it should be controlled directly. The same argument applies to application-level queues: a large queue with low latency is fine; a small queue with high sojourn time is the failure.

**Amazon Web Services, "Using load shedding to avoid overload."** The essay describes the unbounded-queue trap in production terms: a service that accepts all work and queues it will eventually exhaust memory or deliver all responses after the client has timed out. The essay recommends bounded queues with explicit rejection as the baseline and notes that the queue bound should be derived from the SLO, not from memory limits.

## Mitigations

### Bounded queue with deadline-proportional sizing

**What it is:** Set queue capacity = drain_rate × (SLO_deadline − min_service_time). Items beyond this position cannot be served within the deadline; reject them at admission.

**Cost:** Requires knowing the SLO deadline and estimating drain rate; adds a rejection path on every enqueue.

**How it backfires:** Drain rate varies; a queue sized for p50 drain rate will reject items that would succeed at p25 drain rate. Under high variance, the bound is frequently wrong in both directions.

### Adaptive LIFO under load

**What it is:** Maintain queue depth as a signal. When queue depth exceeds a threshold T₁, switch to LIFO. When depth falls below T₂ (T₂ < T₁), revert to FIFO.

**Cost:** Items that arrived early may be indefinitely delayed while the queue is in LIFO mode. Applications where request ordering matters (e.g., sequenced writes) cannot use LIFO.

**How it backfires:** Old high-priority items that arrived just before the overload event will be served last in LIFO mode, potentially missing their deadline. Priority must be tracked explicitly if LIFO is combined with prioritization.

### CoDel active queue management

**What it is:** Track sojourn time (time between enqueue and dequeue attempt) for each item. Drop items whose sojourn time exceeds a target for a sustained interval (e.g., 5ms sojourn target, 100ms sustained interval).

**Cost:** More implementation complexity than a simple bound; the two tuning parameters (target and interval) are workload-specific.

**How it backfires:** In bursty workloads, CoDel may drop items during a brief queue spike that would have cleared quickly. The sustained-interval criterion reduces false positives but doesn't eliminate them.

## Interactions

- [Goodput Collapse](goodput-collapse.md) — unbounded queues allow collapse to deepen by accumulating dead work.
- [Backpressure](backpressure.md) — the queue is the coupling point between producer and consumer; queue depth is the backpressure signal.
- [Deadline Propagation](deadline-propagation.md) — deadline-aware queues can evict expired items before a worker dequeues them; this requires deadline metadata on each item.
- [Load Shedding](load-shedding.md) — shedding at admission prevents items from entering the queue; queue management handles items already admitted.

## References

- Nichols, K. and Jacobson, V. "Controlling Queue Delay." *Communications of the ACM* 55(7), 2012.
  The CoDel paper. Explains why queue length is a poor metric and why sojourn time is the correct control variable.
- Amazon Web Services. "Using load shedding to avoid overload." *AWS Builders' Library*.
  Section on queue management describes the bounded-queue approach and its connection to SLO.
- Welsh, M. et al. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." *SOSP 2001*.
  Section 4 covers per-stage queue management and the connection to backpressure.
