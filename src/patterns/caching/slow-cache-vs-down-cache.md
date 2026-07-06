# Slow Cache vs. Down Cache

> **One-liner:** A cache that takes 500ms to respond is more dangerous than one that refuses connections immediately — a fast failure lets the service shed or fall back; a slow response holds threads and connections until the timeout fires.

## Symptom

- Service latency rising gradually, without a corresponding drop in cache hit rate, while cache cluster is "reachable."
- Thread pool exhaustion on the application side: all threads blocked waiting for cache responses that haven't returned.
- Client-side timeouts for cache requests increasing; retries compounding the problem.
- Application service p99 exceeds SLO even though business logic is not slow — time is spent in blocked cache client calls.
- Opposite behavior from "cache down": down cache triggers immediate fallback; slow cache triggers timeout-after-N-seconds fallback.

## Mechanism

**Why slow is harder to handle than down:**

When a cache is unreachable (TCP refused, connection reset), the failure is synchronous and fast. The application receives an error code in microseconds, makes an immediate decision (fall back to origin, return stale, return error), and moves on. The thread is free.

When a cache is slow (connected but not responding promptly), the failure is asynchronous and timed. The application's cache client sends a request and blocks the calling thread. The thread is held for the duration of the slow request — up to the client-side timeout. At even modest parallelism, all threads become bound to in-flight slow requests.

**The thread math:** A service with a 200-thread pool making cache requests with a 1-second client timeout, against a cache taking 800ms per request instead of the usual 0.5ms:

- Normal: 200 threads × 0.5ms per cache call → 0.1 threads bound to cache at any time.
- Slow: 200 threads × 800ms per cache call → 160 threads bound to cache at any time. Only 40 threads free for all other work.

At 2-second timeout with the same slow cache: all 200 threads are bound within the timeout window. Service is fully saturated.

**Compounding factors:**

*Retry on timeout:* If the client retries on timeout, each timed-out request generates another, doubling load on the already-slow cache. See [Retry Storms](../overload/retry-storms.md).

*Connection pool exhaustion:* Cache clients typically use a fixed connection pool. Slow requests hold connections. If the pool is exhausted, new cache requests block waiting for a connection — adding a connection-wait phase before the cache-wait phase.

*Circuit breaker not triggered:* Most circuit breakers trip on errors (TCP errors, explicit error codes). A slow-but-connected cache produces timeouts, not errors. A circuit breaker configured on error rate will not trip on a slow cache; it needs configuration on timeout rate or latency percentile.

**Distinguishing slow vs. down:**

| Signal | Cache Down | Cache Slow |
|--------|-----------|------------|
| Connection error rate | High | Low |
| Timeout rate on cache calls | Low | High |
| Time-to-error for callers | Fast (ms) | Slow (timeout duration) |
| Thread pool saturation | Low | High |
| Fallback activation | Immediate | After timeout fires |

## Real-world sightings

**Nygard, M. "Release It!" (2nd ed., 2018).** Chapter 5 discusses the "slow response" failure mode in detail. Nygard observes that a slowly responding integration point is the most dangerous failure mode because it propagates up the call chain, converting fast local operations into slow ones as threads block cascading. The recommendation is that every integration point (including cache calls) must have a timeout; a connection without a timeout is a bug.

**AWS Builders' Library, "Using timeouts to avoid request pile-up."** The essay covers precisely this failure mode: a dependency that is slow rather than down causes request pile-up on the calling service. The recommended pattern is aggressive client-side timeouts (much tighter than the SLO) combined with fallback on timeout, so that slow dependencies fail fast for the caller.

## Mitigations

### Aggressive client-side timeouts calibrated to SLO

**What it is:** Set the cache client timeout to a small fraction of the overall request SLO — not to the cache's p99 under normal conditions. If the service SLO is 100ms and a cache response normally takes 1ms, a 10ms timeout catches slow-cache failures with 90ms remaining for fallback.

**Cost:** A tight timeout will reject cache responses that are slow but still within the cache's own SLO. Tune based on the *caller's* budget, not the cache's normal performance.

**How it backfires:** Too tight a timeout causes false positives during normal cache GC pauses or network jitter. The timeout fires during a transient spike, triggering unnecessary fallback to the origin and increasing origin load.

### Circuit breaker on timeout rate (not just error rate)

**What it is:** Configure the circuit breaker to count timeouts as failures, not just explicit errors. Trip the breaker when timeout rate exceeds a threshold (e.g., 5% of requests timing out over a 10-second window). A tripped breaker immediately falls back to origin instead of waiting for the timeout duration on each request.

**Cost:** Adds latency sensitivity to the circuit breaker, which can cause false trips during transient cache slowness (GC, rebalancing).

**How it backfires:** A circuit breaker tripped by normal cache GC pauses causes all traffic to hit the origin, potentially overwhelming it. GC pause windows must be excluded or the threshold must be tuned above the normal GC-induced timeout rate.

### Fallback to stale or degraded response on timeout

**What it is:** On cache timeout, instead of promoting to origin fetch, return the last-seen value for this key (if available in local memory), or return a degraded response. Set a short maximum staleness bound.

**Cost:** Requires local in-memory cache (a "local L1" in front of the distributed cache), or requires the application to handle degraded responses explicitly.

**How it backfires:** Stale data returned after a slow-cache event may be arbitrarily old if local memory isn't refreshed frequently. Without a staleness bound, a cache that is slow for 24 hours serves 24-hour-old data.

## Interactions

- [Cache as Hard Dependency](cache-as-hard-dependency.md) — both patterns address cache failure; this page covers the slow (partial) failure mode that is harder to detect.
- [Slow Is Worse Than Down](../dependencies/slow-is-worse-than-down.md) — the general pattern of which this is the cache-specific instance.
- [Retry Storms](../overload/retry-storms.md) — retrying on timeout against a slow cache amplifies the load on the already-slow cache.
- [Adaptive Concurrency](../overload/adaptive-concurrency.md) — an adaptive concurrency limit reacts to increased latency, reducing in-flight count when the cache is slow, preventing thread exhaustion.

## References

- Nygard, M. *Release It!* 2nd ed. Pragmatic Programmers, 2018.
  Chapter 5 covers slow response as the most dangerous integration failure mode; Chapter 4 covers circuit breakers.
- Amazon Web Services. "Using timeouts to avoid request pile-up." *AWS Builders' Library*.
  Concrete guidance on timeout calibration and fallback behavior for dependencies including caches.
