# Queue Sizing

> **One-liner:** Every item that can sit in a queue commits to latency for everything behind it — the right queue depth is `service_rate × deadline`, and everything beyond that is doomed work you're still paying to carry.

## Symptom

- Queue length growing over time during sustained load.
- p99 latency proportional to queue depth — requests that wait in queue for a long time before processing started.
- Items timing out before reaching a worker (measured as deadline exceeded errors, not slow processing errors).
- After a load spike ends, tail latency persists for minutes as the queue drains.
- Long queue draining causes "latency hangover": load is gone but responses are slow for the queue's drainage time.

## Mechanism

**Little's Law applied to queues:**

By Little's Law: L = λW, where L is mean queue depth, λ is arrival rate, and W is mean sojourn time (wait + service). If items arrive at λ and service takes 1/μ per item at a single server, the waiting time for the L-th item in queue is L/μ.

For a queue with capacity Q, the worst-case waiting time for an admitted item is Q/μ. If the SLO is deadline D, then the maximum queue depth that allows all admitted items to meet the deadline is:

```
Q_max = μ × D     (deadline-proportional queue size)
```

Items arriving when queue depth > Q_max will not complete within deadline. Continuing to admit and process them wastes service capacity on doomed work while blocking items that might have made the deadline (if the queue were shorter).

**The latency hangover effect:**

Suppose Q = 10,000 and service rate μ = 100/s. Drain time from full = 100 seconds. If the load spike lasts 10 seconds and then returns to below service rate, the queue stops growing but takes 100 seconds to drain. During those 100 seconds, every request waits up to 100 seconds — long after the spike is over.

A smaller queue (Q = 100, drain time = 1 second) would have shed requests during the spike but returned to normal latency within 1 second of the spike ending. The trade-off: smaller queues shed more work during the spike, but recover faster.

**Sizing for variable service rates:**

Service rate μ varies: it may be higher at p50 and much lower at p99 (e.g., if slow requests bottleneck on a common resource). Sizing Q = μ_p99 × D is conservative but correct: it ensures even slow requests can complete within deadline if they are at the front of the queue. Sizing Q = μ_p50 × D is more aggressive: some requests that would have completed within deadline are shed.

In practice: set Q between μ_p50 and μ_p95; monitor the shed rate; adjust based on how much shedding is acceptable.

**Thread pool queues vs. external queues:**

Thread pool queues (e.g., Java's `ArrayBlockingQueue` in `ThreadPoolExecutor`) have a maximum capacity. When full, new submissions are rejected (RejectedExecutionHandler fires). This is a natural queue size cap; the default unbounded queue (`LinkedBlockingQueue`) is an antipattern for latency-sensitive services.

External queues (Kafka, SQS, Redis) are often effectively unbounded. For latency-sensitive consumers, the consumer should check the message's enqueue timestamp and discard messages older than the deadline — the message is already doomed when it's dequeued.

## Real-world sightings

**Amazon SQS visibility timeout and message age.** SQS does not have a built-in per-message deadline, but the `ApproximateAgeOfOldestMessage` CloudWatch metric indicates how long the oldest message in the queue has been waiting. AWS documentation recommends alerting on this metric and, for latency-sensitive queues, consumers should filter by message age and discard messages older than the SLO deadline.

**Kubernetes resource limits and request queues.** Kubernetes API server requests are queued in priority and fairness (APF) flow schemas, each with a configurable queue depth and concurrency limit. The `kube-apiserver` documentation notes that queue depth should be sized relative to the server's throughput and the acceptable request latency, directly applying the Q_max = μ × D principle.

## Mitigations

### Deadline-proportional queue cap

**What it is:** Set the queue capacity Q = μ × D, where μ is the service rate and D is the request deadline. Reject or shed items that arrive when the queue is at capacity. This guarantees that admitted items that survive to service will complete within deadline.

**Cost:** Requires knowing μ and D. μ must be estimated and may vary. Shedding generates errors that callers must handle.

**How it backfires:** If μ drops (e.g., a slow upstream dependency), the effective Q_max shrinks but the configured cap stays the same. A queue set at μ_normal × D now admits more items than can complete within deadline under degraded throughput. Monitor effective service rate and alert when it deviates from the baseline used for sizing.

### Message age check at dequeue (for external queues)

**What it is:** When consuming from an external queue (Kafka, SQS, Redis), check the message's enqueue timestamp before processing. If age > deadline, discard the message without processing it. This prevents the consumer from doing work on requests that are already timed out from the caller's perspective.

**Cost:** Requires a timestamp in the message payload or a message attribute. Discarded messages may need to be tracked for observability (dropped message rate metric).

**How it backfires:** If the clock between producer and consumer is skewed, message age calculations are wrong. Use monotonic timestamps from a synchronized source (NTP-synchronized system clocks are usually sufficient for second-granularity deadlines).

### Graduated shedding before queue full

**What it is:** Begin shedding before the queue reaches capacity. At 80% of Q_max, start probabilistic shedding (10% of arrivals). At 90%, shed 30%. At 100%, shed 100%. This prevents the queue from oscillating between full and empty; graduated shedding reduces the latency impact of a spike by shedding early.

**Cost:** Some requests are shed that would have been processed within deadline. The shed rate must be tuned to the expected spike duration.

**How it backfires:** If shedding is too aggressive (starts too early at too high a rate), valid requests are dropped unnecessarily. If too conservative, the queue fills and the latency hangover effect occurs before shedding kicks in.

## Interactions

- [Queue Management](../overload/queue-management.md) — queue management policies (FIFO, LIFO, LIFO with probe, CoDel) determine which items are shed when the queue is at capacity; queue sizing determines when shedding activates.
- [Batching](batching.md) — queue between arrival and batch assembly; sizing must account for batch fill time in the sojourn time calculation.
- [Backpressure](../overload/backpressure.md) — queue size limit is the backpressure signal; when the limit is reached, the upstream must slow down or shed.
- [Deadline Propagation](../overload/deadline-propagation.md) — the per-request deadline D used in Q = μ × D must be the remaining deadline at queue entry, not the original SLO; long-queued items should have less remaining deadline.

## References

- Little, J.D.C. "A Proof for the Queuing Formula: L = λW." *Operations Research 9(3)*, 1961.
  The original proof of Little's Law; the Q_max = μ × D derivation follows directly.
- Nichols, K. and Jacobson, V. "Controlling Queue Delay." *ACM Queue 10(5)*, 2012.
  Introduces CoDel (Controlled Delay), an active queue management algorithm that sheds based on sojourn time rather than queue length — the queue-size-as-latency-commitment insight in algorithmic form.
