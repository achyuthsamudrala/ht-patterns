# Slow Is Worse Than Down

> **One-liner:** A dependency that fails instantly lets callers fail fast and free their threads; a dependency that responds slowly holds threads until they time out, exhausting the caller's capacity.

## Symptom

- Thread pool or connection pool exhaustion on the calling service while the dependency appears "up."
- CPU low on the caller; all threads blocked waiting on a slow downstream.
- p99 on the caller rising proportionally to the dependency's timeout duration (not the dependency's actual latency).
- Downstream shows high latency but not errors from its own perspective.
- Setting a shorter timeout on the caller immediately frees capacity.
- Caller error rate spikes as threads exhaust and new requests can't be scheduled.

## Mechanism

**The asymmetry between down and slow:**

When a dependency is down (TCP refused, connection reset), the failure is synchronous and instantaneous. The caller catches the error in microseconds, executes its fallback or error path, and the thread is free. Total time consumed: the TCP handshake timeout (typically under 1ms with keepalives).

When a dependency is slow (connected but not responding promptly), the failure is asynchronous. The caller sends a request, and the connection stays open. The thread waits. If the thread is blocking, it's held for the entire duration — up to the client-side timeout. If that timeout is 30 seconds, a thread is held for 30 seconds on each slow request.

**Little's Law applied:** By Little's Law, threads_in_use = RPS × response_time. At 100 RPS with normal 10ms dependency response: 100 × 0.01 = 1 thread bound to that dependency at any time. At 100 RPS with 5-second dependency latency: 100 × 5 = 500 threads bound — more than most thread pools total.

**The saturation cascade:**
1. Dependency slows; response time increases from 10ms to 5 seconds.
2. Threads accumulate waiting: 500 threads bound to slow dependency.
3. Thread pool exhausts; new requests queue.
4. Queue fills; new requests are rejected with errors.
5. Caller's error rate spikes; health checks may fail.
6. Caller itself is taken out of the load balancer (marked unhealthy).
7. Remaining callers receive more traffic; they saturate faster.

**The monitoring gap:** Most monitoring alerts on error rates, not latency distributions. A slow dependency that eventually returns 200 OK (within its own timeout) generates no errors, no alerts — only thread exhaustion that appears as an unrelated capacity issue. This gap is why incidents involving slow dependencies are frequently diagnosed incorrectly as "overload" on the caller.

**Async callers are not fully immune:** Event-loop architectures (Node.js, async Python, Netty) don't block threads on IO, but they bind event loop capacity to pending callbacks. A slow dependency at high request rate fills the pending callback queue and delays all other work through head-of-line blocking on the event loop.

## Real-world sightings

**Nygard, M. "Release It!" (2nd ed., 2018).** Chapter 5 introduces the "integration points" antipattern with exactly this framing: a slow integration point is more dangerous than a down one because it doesn't produce the signals that trigger failover. The entire pattern catalog in Nygard's book (timeouts, circuit breakers, bulkheads) is structured around defending against slow dependencies rather than down ones.

**AWS Builders' Library, "Timeouts, retries, and backoff with jitter."** The essay explicitly states: "If you don't add timeouts, a single hanging dependency can consume all your threads and make your entire service unavailable." This formulation matches the thread exhaustion cascade above.

## Mitigations

### Aggressive timeouts calibrated to the SLO budget

**What it is:** Set dependency timeouts to a fraction of the caller's own SLO, not to the dependency's p99 latency. If the caller's SLO is 500ms and the dependency normally responds in 5ms, a 50ms timeout (10× normal) catches slowness while leaving 450ms for fallback, error handling, and response.

**Cost:** Timeouts shorter than the dependency's p99 latency will reject responses that would have succeeded. Tune based on the caller's budget, not the dependency's characteristics.

**How it backfires:** Dependencies that are normally fast but have occasional high-percentile spikes (GC pauses, lock contention) will produce false-positive timeouts. A 50ms timeout with a GC-pause dependency at 100ms GC pause = guaranteed false positives every GC cycle.

### Bulkheads for each dependency

**What it is:** Isolate each dependency behind its own thread or connection pool. A slow dependency exhausts only its own pool; other dependencies and local work are unaffected. See [Bulkheads](bulkheads.md).

**Cost:** Total thread count grows with number of dependencies; each pool must be sized correctly.

**How it backfires:** Under-sizing a pool causes legitimate requests to be rejected even when the dependency is healthy. Over-sizing defeats the isolation purpose.

### Circuit breaker on latency percentile

**What it is:** Monitor the dependency's latency distribution. When p99 exceeds a threshold, open the circuit breaker: future calls fail immediately (fast) rather than slow. The breaker periodically allows probe requests through to detect recovery.

**Cost:** Adds state and complexity; requires tuning the latency threshold and probe interval.

**How it backfires:** A circuit breaker that opens during normal p99 latency spikes (e.g., from GC) blocks legitimate traffic and can cause cascading failure on the caller. The threshold must be set above normal variance but below the danger zone.

## Interactions

- [Bulkheads](bulkheads.md) — the structural containment for slow dependency blast radius.
- [Slow Cache vs. Down Cache](../caching/slow-cache-vs-down-cache.md) — the cache-specific instance of this pattern.
- [Adaptive Concurrency](../overload/adaptive-concurrency.md) — adaptive concurrency limits react to latency increase, shedding load before thread exhaustion.
- [Deadline Propagation](../overload/deadline-propagation.md) — propagating deadlines downstream prevents zombie work from accumulating even when the dependency is slow.

## References

- Nygard, M. *Release It!* 2nd ed. Pragmatic Programmers, 2018.
  Chapter 5 defines the "integration point" antipattern and motivates timeouts, circuit breakers, and bulkheads as the three necessary defenses.
- Amazon Web Services. "Timeouts, retries, and backoff with jitter." *AWS Builders' Library*.
  Practical guidance on timeout calibration; the thread exhaustion cascade is described in the section "Why timeouts are important."
- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  Chapter 15 covers the M/G/c queue model that formalizes why response-time variance (slow responses) is more costly than mean response time.
