# Bulkheads

> **One-liner:** A thread or connection pool shared across dependencies means a slow dependency can exhaust capacity for all dependencies — bulkheads give each dependency its own pool so failures are contained.

## Symptom

- One slow or failing dependency causing failures on unrelated requests that don't use it.
- Thread pool full; all threads waiting on a single downstream; unrelated requests queued.
- Removing or timing out the slow dependency immediately frees capacity for other work.
- Traces show threads waiting on dependency A while requests for dependency B are rejected for lack of threads.

## Mechanism

Named after the watertight compartments in a ship's hull: flooding in one compartment doesn't sink the ship because the bulkheads prevent water from spreading. In software: isolate each external dependency behind its own resource pool (thread pool, connection pool, semaphore) so that failure in one dependency's pool cannot affect others.

**The shared pool problem:** Without bulkheads, all dependencies share the service's thread pool. A typical service with 200 threads making calls to three dependencies (database, cache, recommendation service):

- Normal: each dependency uses ~10 threads, leaving 170 for local work.
- Recommendation service slows (5s latency): 100 RPS × 5s = 500 threads needed → pool exhausted in <2 seconds.
- Result: database and cache requests fail for lack of threads, not because those dependencies are slow.
- User impact: all requests fail, even those that don't use the recommendation service.

**With bulkheads:** Each dependency gets 60 threads. Recommendation service slowness fills its 60-thread pool. Database and cache pools are unaffected. Requests that use the recommendation service fail or degrade; requests that don't use it continue normally.

**Pool sizing as a design decision:** Bulkhead sizing encodes a capacity commitment: "I will allocate at most N threads to dependency X." The N must be:
- Large enough to absorb normal load at p99 latency: N ≥ RPS × p99_latency.
- Small enough that the rest of the service has adequate threads: sum(N_i) ≤ total_threads - headroom.

**Semaphore-based bulkheads:** Instead of separate thread pools, use a per-dependency semaphore with limit N. Each request acquires the semaphore before calling the dependency and releases it after. This prevents resource allocation for dependency calls while allowing the calling thread to fail fast (rather than waiting in a thread pool queue).

Semaphore bulkheads don't prevent thread exhaustion from slow dependencies (the calling thread still blocks). They prevent the number of concurrent slow calls from exceeding N, bounding the maximum thread exhaustion.

**Thread pool bulkheads:** Execute dependency calls on a dedicated thread pool. The calling thread submits a task and waits (with a timeout) for the result. This fully isolates the dependency's thread consumption from the caller's pool.

Thread pool bulkheads add context-switching overhead (submitting to and waiting on a thread pool) and increase memory (separate stacks per thread). They provide the strongest isolation.

## Real-world sightings

**Netflix Hystrix.** Netflix developed Hystrix in 2011 and open-sourced it in 2012 as the canonical implementation of the bulkhead pattern for JVM microservices. The library was built after Netflix observed in production that slow downstream calls (particularly to recommendation and personalization services) would exhaust shared thread pools, causing failures across unrelated request paths. Hystrix wrapped each downstream call in a thread pool bulkhead, with circuit breakers and fallback logic.

**Beyer et al., "Site Reliability Engineering" (2016).** Chapter 22 covers bulkheads in the context of cascading failure prevention. The book describes a pattern at Google where shared connection pools to storage backends caused failures to cascade: a storage backend's slowness would saturate the pool shared with other storage backends, causing all storage access to fail even on healthy backends.

## Mitigations

### Per-dependency thread pool

**What it is:** Execute each dependency call on a dedicated thread pool. The calling thread submits the task, awaits the result (with a timeout), and handles failure if the pool is full or the task times out.

**Cost:** Memory overhead per thread (stack space); context-switching overhead; each pool must be individually sized.

**How it backfires:** If a pool is sized too small, legitimate requests are rejected with "pool full" errors even when the dependency is healthy. Under-sizing is the dominant failure mode.

### Per-dependency semaphore

**What it is:** Use a counting semaphore to cap concurrent calls to each dependency at N. The calling thread acquires the semaphore before calling the dependency; fails fast (without calling) if the semaphore is already at max.

**Cost:** Lower overhead than thread pool bulkheads; the calling thread still blocks on the dependency.

**How it backfires:** Semaphores prevent *new* calls from being initiated but don't interrupt in-flight calls. An already-in-flight slow call still holds the thread. At max semaphore count, all acquired threads are blocking on slow responses.

### Combined bulkhead and circuit breaker

**What it is:** Use a bulkhead to limit concurrency AND a circuit breaker to stop calling a dependency that is consistently slow. The bulkhead limits damage while the circuit breaker is closing; the circuit breaker prevents the pool from filling in the first place once the dependency is known to be slow.

**Cost:** Two components to configure and monitor; circuit breaker state must be communicated across threads.

**How it backfires:** A circuit breaker that opens too eagerly (low threshold) combined with a bulkhead means neither correctly-responding calls nor recoveries are attempted.

## Interactions

- [Slow Is Worse Than Down](slow-is-worse-than-down.md) — bulkheads contain the blast radius of slow dependencies.
- [Criticality Tiers](criticality-tiers.md) — pool sizes should reflect criticality: tier-1 dependencies get larger pools; tier-3 get smaller pools with aggressive circuit breakers.
- [Correlated Failure](correlated-failure.md) — bulkheads prevent intra-service correlation (one dependency affecting another); correlated failure is the inter-service equivalent.

## References

- Netflix. "Introducing Hystrix for Resilience Engineering." *Netflix Technology Blog*, 2012.
  Describes the motivation and implementation of thread pool bulkheads; the post includes production metrics showing failure containment.
- Nygard, M. *Release It!* 2nd ed. Pragmatic Programmers, 2018.
  Chapter 5 introduces the bulkhead pattern; Chapter 4 covers how bulkheads interact with circuit breakers.
- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 22 covers bulkheads in the context of cascading failure.
