# Mixed Request Patterns

> **One-liner:** Large requests head-of-line-block small ones in a shared queue — a single 10-second export occupying the only available thread delays hundreds of sub-millisecond lookups behind it.

## Symptom

- Sporadic latency spikes on fast endpoints that correlate with submissions of large or slow requests.
- Per-request latency histograms bimodal: a fast mode and a slow mode; the slow mode corresponds to queuing behind large requests.
- Thread pool utilization high on a few threads (executing long requests) while many requests queue.
- Adding more threads reduces the problem temporarily but the head-of-line effect returns at higher load.

## Mechanism

**HOL blocking mechanics in thread pools:**

In a shared thread pool of size N, if K threads are executing long-running requests (K ≤ N), only N−K threads are available for short requests. Short requests queue behind long ones. In the extreme case (K = N), no threads are available; the queue grows unbounded.

Example: Thread pool = 100 threads, 80 requests executing synchronous exports (10s each), 20 threads available.
- 500 RPS of 10ms lookups arrive. Each thread can handle 1000 ms / 10 ms = 100 lookups/second.
- Capacity: 20 threads × 100 = 2,000 lookups/second (fine, exceeds load).
- But now the 80 export threads finish and return to the pool. The exports start again. At 80/s export rate (possible at 500 RPS if 16% of requests are exports), all 100 threads immediately fill with exports.
- Lookups: 0 available threads. Queue grows at 500 requests/second.

The system is not CPU-saturated (exports are IO-bound). It is queue-saturated due to size class mixing.

**Size class skew:** The problem is worse when request latency distribution is heavy-tailed. If 99% of requests complete in 10ms and 1% take 10s, and there are 100 threads:
- At 5,000 RPS: 50 requests always in-flight. ~0.5 are 10s requests.
- 1% of 50 = 0.5 threads occupied by slow requests on average → minimal effect.
- At 50,000 RPS: 500 requests in-flight → 5 threads occupied by slow requests → 5% capacity reduction.
- At 500,000 RPS: 50 threads occupied by slow requests → 50% capacity reduction.

The HOL blocking effect scales with both the fraction of long requests and the overall load.

**Mixing in event loops:**

Event-loop models (Node.js, async Python, Go) have the same problem but expressed differently: a single blocking operation on the event loop (a CPU-bound computation or a blocking syscall) prevents all callbacks from running. The async analogue of HOL blocking is a blocking call on the main event loop. Fix: offload CPU-bound or blocking IO to a separate goroutine/worker thread.

## Real-world sightings

**SEDA (Staged Event-Driven Architecture), Welsh et al. (2001).** SEDA introduced the idea of separate thread pools per stage specifically to isolate different request classes. The paper shows that in a unified thread pool, bursty long-running requests starve short ones. Per-stage pools with independent queues prevent cross-class HOL blocking.

**Elasticsearch bulk vs. search traffic.** Elasticsearch separates bulk indexing and search into different thread pool categories. By default, search uses the `search` thread pool and bulk uses the `write` thread pool. Without this separation, heavy bulk indexing monopolizes threads and degrades search latency.

## Mitigations

### Size class thread pools

**What it is:** Separate thread pools for different request size classes. Route requests to the appropriate pool based on estimated execution time: short requests (< 100ms) to pool A, long requests (> 1s) to pool B. Each pool has an independent queue and independent size. Pool B is usually smaller (fewer concurrent long requests are needed to saturate the system).

**Cost:** Thread pool proliferation. Routing logic must estimate request size before admission — not always possible.

**How it backfires:** If the size estimate is wrong (a request thought to be short turns out long), it occupies a thread in the wrong pool. Size reclassification mid-execution is generally not possible without a coroutine or checkpoint mechanism.

### Request time limits and preemption

**What it is:** Set a maximum execution time for requests in each pool. A request that exceeds its time limit is cancelled (or moved to a long-running pool). This prevents a small number of unexpectedly long requests from monopolizing threads in a pool designed for short requests.

**Cost:** Cancelled requests are failed; callers must retry or receive error responses.

**How it backfires:** Cancellation requires cooperative cancellation (the handler must check for cancellation at checkpoints). A handler that blocks on an IO call with no timeout cannot be cancelled until the IO completes.

### Admission control on long-running paths

**What it is:** Apply separate admission control to long-running request paths. Limit concurrent long-running requests to a concurrency ceiling (e.g., max 20 simultaneous exports). Requests that arrive when the ceiling is full are rejected (503) or queued, rather than admitted and consuming a thread from the shared pool.

**Cost:** Long-running requests can be rejected during load peaks. Users must retry or receive an error.

**How it backfires:** A ceiling too low throttles legitimate work; too high allows HOL blocking to reappear. Must be tuned to balance long-request throughput with short-request latency.

## Interactions

- [Fair Scheduling](fair-scheduling.md) — separate queues per request class enable fair scheduling within each class independently.
- [Bulkheads](../dependencies/bulkheads.md) — the same thread pool separation pattern applies to dependency isolation: separate pools for fast vs. slow dependencies.
- [Staged Architectures](../pipeline/staged-architectures.md) — SEDA formalizes per-stage pools; each stage has a single request class.
- [Slow Request Isolation](../tail-latency/slow-request-isolation.md) — tail latency view of the same problem; HOL blocking is the mechanism.

## References

- Welsh, M. et al. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." *SOSP 2001*.
  The foundational paper on staged architectures with per-stage pools; directly addresses HOL blocking in mixed workloads.
- Elasticsearch. "Thread pools." *Elasticsearch Documentation*.
  Describes the default thread pool categories and how to configure them for workload isolation.
