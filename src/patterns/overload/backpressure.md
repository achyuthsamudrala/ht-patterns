# Backpressure

> **One-liner:** Signal producers to slow down when the consumer is falling behind — the alternative is unbounded queuing until memory is exhausted or goodput collapses.

## Symptom

*Symptoms indicating backpressure is absent:*

- Queue depth growing without bound under sustained load.
- Memory climbing on the consumer host as queued work accumulates.
- Producer throughput unaffected while consumer is saturated.
- OOM kills or disk-full errors on the consumer from work accumulation.

*Symptoms of well-functioning backpressure:*

- Producer throughput drops when consumer slows, then recovers when consumer recovers.
- Queue depth stays bounded under sustained load.
- End-to-end latency increases under load (correct: producers are waiting), rather than queue depth exploding.

*Symptoms of broken backpressure:*

- Backpressure is configured but producers ignore it (no signal propagation).
- Backpressure causes deadlock: producer and consumer share a thread pool; backpressure blocks producers in the same pool that drains the consumer queue.

## Mechanism

Backpressure is the mechanism by which a consumer signals its upstream producers to reduce their production rate. Without it, a slow consumer accumulates unbounded queue depth, which increases per-item sojourn time and eventually causes OOM or [Goodput Collapse](goodput-collapse.md).

With backpressure, the consumer's capacity sets a natural bound on the production rate. When the consumer is slow, the signal propagates upstream, and producers slow to match consumer capacity. This is [Little's Law](../../foundations/littles-law.md) working correctly: L (in-flight) = λW, and if W increases, λ must decrease to keep L bounded.

**In synchronous request-response systems (HTTP, gRPC):** Backpressure is implicit. When the server's thread pool is full, new connection attempts block (or are refused). The client blocks waiting for a connection, which slows its production rate. This works as long as the client can afford to block. If the client is event-driven or has its own SLO, blocking is not backpressure — it's congestion.

**In message queue systems (Kafka, RabbitMQ):** Backpressure is not automatic. The queue accepts messages at the producer's rate regardless of consumer throughput. Consumer lag (the gap between producer offset and consumer offset) is the observable. Backpressure must be implemented explicitly: the producer reads consumer lag and slows if lag exceeds a threshold, or the queue operator imposes topic-level size limits.

**In async frameworks (Reactive Streams, gRPC flow control, HTTP/2 flow control):** Backpressure is built into the protocol. The consumer grants the producer credit (a number of items it's ready to receive). The producer sends up to that credit and then waits for more. This is the most robust form but requires both sides to implement the credit protocol.

**The deadlock trap:** A common mistake is implementing backpressure by blocking the producer thread when the queue is full, when the producer and consumer share the same thread pool. The consumer needs a free thread to drain the queue; the blocked producer holds a thread in the pool; the pool exhausts; the consumer can't get a thread to drain; deadlock.

The fix: use a dedicated drain thread pool separate from the production thread pool, or use non-blocking rejection rather than blocking.

## Real-world sightings

**Reactive Streams specification (reactive-streams.org).** Developed jointly by Netflix, Lightbend, Twitter, and others in 2013–2014 to address the absence of standard backpressure in async JVM systems. The specification was developed precisely because existing async frameworks (RxJava 1.x, Akka Streams 1.x) did not propagate backpressure, leading to producers overwhelming consumers in production services. The specification's demand-signaling model became the basis for Java 9's `java.util.concurrent.Flow`.

**Welsh, M. et al., SEDA (SOSP 2001).** The staged event-driven architecture paper explicitly identifies backpressure as the mechanism that keeps per-stage queues bounded. Without per-stage backpressure, a slow stage's queue grows without bound, eventually exhausting the server's memory. SEDA's per-stage controller monitors queue depth and applies backpressure to upstream stages when depth exceeds a threshold.

## Mitigations

### Bounded queues with blocking or rejection

**What it is:** Cap queue depth. When full, either block the producer (blocking backpressure) or reject the item (load shedding). Rejection is usually preferable to blocking; see the deadlock trap above.

**Cost:** Rejection requires the producer to handle rejection gracefully. Blocking requires the producer to be able to block without causing higher-level deadlocks.

**How it backfires:** Bounded queues with rejection are only as good as the upstream's ability to handle rejection. A producer that retries immediately on rejection just re-enqueues the same work, keeping the queue full. See [Retry Storms](retry-storms.md).

### Credit-based flow control

**What it is:** Consumer grants producer a number of items (credits) it's ready to receive. Producer sends up to that count and waits. Consumer grants more credits as it drains.

**Cost:** Both sides must implement the credit protocol. Adds round-trip latency on the credit-grant path.

**How it backfires:** If the credit-granting path is on the slow consumer, and the consumer is slow because it's overloaded, credit grants may be delayed, causing unnecessary producer stalls even when the consumer has partially recovered.

### Upstream rate limiting based on consumer lag

**What it is:** Producer monitors consumer lag (or consumer-reported queue depth) and reduces production rate when lag exceeds a threshold.

**Cost:** Requires consumer lag observability; adds rate-limiting logic to the producer.

**How it backfires:** Lag monitoring is coarse; a producer that sees lag every 10 seconds may overshoot in either direction before correcting.

## Interactions

- [Queue Management](queue-management.md) — the queue is the medium through which backpressure is communicated; queue policy determines what happens when the queue fills.
- [Load Shedding](load-shedding.md) — shedding rejects at the consumer entry point; backpressure signals the producer to slow before reaching the consumer.
- [Staged Architectures](../pipeline/staged-architectures.md) — per-stage backpressure is SEDA's defining mechanism.
- [Goodput Collapse](goodput-collapse.md) — absent backpressure allows producers to drive consumers into collapse.

## References

- reactive-streams.org. "Reactive Streams Specification." 2014.
  Defines the demand-signaling backpressure protocol for async JVM systems. The preamble explains why backpressure is necessary and what breaks without it.
- Welsh, M. et al. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." *SOSP 2001*.
  Section 4 describes per-stage backpressure as the mechanism that keeps staged systems well-conditioned under load.
- Akidau, T. et al. "The Dataflow Model." *VLDB 2015*.
  Section on watermarks and progress tracking in streaming systems; the backpressure model generalizes to this setting.
