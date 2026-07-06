# Slow Request Isolation

> **One-liner:** A single slow request holding a thread blocks all faster requests queued behind it — isolating slow work to a dedicated pool eliminates head-of-line blocking for the fast path.

## Symptom

- p99 rising, correlated with arrivals of specific request types: large payloads, complex queries, or requests from specific tenants.
- Fast-path requests timing out even though fast-path handlers complete quickly — they're queued behind slow requests waiting for a thread.
- Thread pool or connection pool exhaustion coincides with bursts of expensive requests, not overall traffic increases.
- Traces show short-lived requests queuing for long periods before execution begins, despite the server not appearing overloaded by CPU metrics.

## Mechanism

**Head-of-line blocking in a shared thread pool:** A service's thread pool processes all incoming requests. When a small number of expensive requests (high compute cost, large I/O, long-held locks) arrive, they occupy threads for seconds. Concurrently arriving cheap requests queue waiting for threads. The cheap request's observed latency = queue wait + processing time. Queue wait is dominated by the slow requests ahead of it.

**The math:** At 200 threads, 10 slow requests each taking 5 seconds occupy 10 threads for 5 seconds. During those 5 seconds, at 500 RPS, 2,500 fast requests arrive. With 190 remaining threads draining at 10ms/request, the throughput is 190 threads × 100 req/s = 19,000 req/s — sufficient. But if slow requests arrive in bursts (20 simultaneously), they occupy 20 threads for 5s. With 2,500 fast requests arriving in 5 seconds against 180 threads × 100 req/s = 18,000 cap, there's no queuing. But at 30 slow requests simultaneously, the math changes.

More critically: the problem is not throughput but latency. A fast request that arrives when 10 threads are held by slow requests must wait in the queue. If the queue has 100 fast requests ahead of it plus 10 slow requests, it waits behind both.

**The asymmetry:** Fast requests and slow requests do not have the same thread-holding time. Putting them in the same queue means fast requests sometimes wait behind slow ones — a classic head-of-line (HOL) blocking problem. HOL blocking is also the problem that HTTP/2 multiplexing addresses at the protocol level, and that TCP HOL blocking causes in stream-based protocols.

**Sources of request cost variance:**
- *Payload size:* Serialization, deserialization, compression scale with payload.
- *Query complexity:* Database queries scanning more rows take longer.
- *Tenant characteristics:* A tenant with 10M records vs. one with 100 records.
- *Cache miss vs. hit:* Cache miss requests go to origin; cache hits return immediately.
- *Request type:* Read vs. write, simple vs. aggregate.

**Isolation strategies:**

*By request type:* Route known-expensive request types (e.g., "export" vs. "lookup") to dedicated pools at the routing layer.

*By tenant:* Route high-cost tenants to a dedicated pool; protect other tenants from HOL blocking. See multitenancy patterns.

*By measured cost:* Use a fast cost estimator (payload size, query plan estimate) to classify requests at admission and route to pools dynamically.

## Real-world sightings

**Amazon Web Services, "Avoiding overload in distributed systems by putting the smaller service in control."** The Builders' Library essay discusses how Amazon separates "work" requests (fast, interactive) from "admin" requests (slow, batch) into different queues. Without separation, a batch of admin work processing large datasets can cause interactive requests to time out even though the service has capacity.

**Envoy Proxy priority queues.** Envoy implements request prioritization at the HTTP/2 stream level: streams can be assigned HIGH, DEFAULT, or LOW priority. The scheduler processes high-priority requests first, preventing low-priority (typically heavier) requests from occupying connection capacity ahead of interactive requests. This is HOL blocking mitigation at the connection layer.

## Mitigations

### Dedicated slow-request thread pool

**What it is:** Identify request types known to be slow at design time. Route these types to a separate thread pool with a lower concurrency limit. Fast request types route to the primary pool and are never queued behind slow requests.

**Cost:** Total thread count grows. Each pool must be individually sized. Misclassification of a slow request as fast contaminates the fast pool.

**How it backfires:** If slow requests are more common than expected, their dedicated pool saturates while the fast pool is underutilized. Capacity cannot be shifted between pools without reconfiguration. Under traffic shifts, the split may be wrong in both directions simultaneously.

### Admission-time cost classification

**What it is:** At admission, estimate the request's execution cost using observable features (payload size, user-specified parameters, query plan estimate). Route to a pool based on the cost estimate: cheap to fast pool, expensive to slow pool.

**Cost:** The cost estimator must be fast (adds to request latency). A bad estimator mis-routes requests, causing either fast-pool contamination or over-routing to the slow pool.

**How it backfires:** Cost estimates are computed before execution; actual cost may differ. A query that looks cheap (small filter set) but accesses non-indexed columns may be very expensive at execution time. The estimator must be tuned for the actual cost distribution.

### Priority-aware scheduling at the queue

**What it is:** Instead of FIFO per pool, use priority queues where fast-path requests have higher priority and are dequeued ahead of slow-path requests when a worker becomes free.

**Cost:** Adds priority assignment to every request; queue implementation becomes more complex.

**How it backfires:** Low-priority (slow) requests are starved when high-priority load is continuous. A slow request that keeps being preempted never completes, consuming memory in the queue indefinitely.

## Interactions

- [Queue Management](../overload/queue-management.md) — bounded FIFO queues have this HOL blocking problem; adaptive LIFO or priority queues reduce it.
- [Hedged Requests](hedged-requests.md) — hedging doesn't help if slowness is due to request cost rather than stochastic server-side variance.
- [Variance Sources](variance-sources.md) — some variance sources (payload size) are predictable and amenable to isolation; others (GC) are not.

## References

- Amazon Web Services. "Avoiding overload in distributed systems by putting the smaller service in control." *AWS Builders' Library*.
  Describes queue separation between fast and slow request types; the concrete Amazon internal case study.
- Ousterhout, J. et al. "Eliminating Receive Livelock in an Interrupt-Driven Kernel." *USENIX ATC 1996*.
  Classic paper on HOL blocking in OS networking; the same principle applies to application-level queues.
- Welsh, M. et al. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." *SOSP 2001*.
  Staged architecture explicitly separates fast and slow request paths into different stages with different queue policies.
