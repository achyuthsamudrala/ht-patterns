# Concurrency Models

> **One-liner:** Blocking I/O on an event loop holds the thread that processes all other requests — thread-per-request models pay thread overhead but contain blast radius; event loops scale higher but any blocking call collapses them.

## Symptom

*Event-loop misuse symptoms:*
- Service is IO-bound; event loop CPU is unexpectedly at 100%.
- All concurrent requests slow when one request does blocking work.
- p50 and p99 latency spike together — all requests delayed equally — suggesting a single bottleneck serializing execution.

*Thread-per-request saturation symptoms:*
- Thread pool full; new requests queuing; CPU is low (threads are blocked, not executing).
- OOM from too many threads at high concurrency (each thread's stack consumes memory).
- Threads blocked waiting on slow dependencies. See [Slow Is Worse Than Down](../dependencies/slow-is-worse-than-down.md).

## Mechanism

**Thread-per-request:**

Each incoming request is assigned a dedicated thread from a pool. The thread handles the request from start to finish, blocking on I/O calls. When the request completes, the thread returns to the pool.

Properties:
- *Simple mental model:* sequential code; stack traces are meaningful; blocking is safe.
- *Resource bound:* scales to thread pool size. Beyond that, new requests queue. Memory: each thread consumes 256KB–8MB of stack; a pool of 1,000 threads uses 256MB–8GB.
- *I/O wait is safe:* a blocked thread is just waiting; it doesn't prevent other requests from being handled.
- *Capacity formula:* max concurrent requests = thread pool size. By Little's Law, for a service with 200ms average latency and 100 threads: max RPS = 100 / 0.2 = 500 RPS.

**Event loop (non-blocking / async):**

A small number of threads (often 1 per CPU core) run an event loop. All I/O is non-blocking and callback-based (or async/await-based). The thread handles a callback, yields control, handles another callback.

Properties:
- *Very high concurrency:* one thread can handle thousands of concurrent connections (no per-connection thread overhead).
- *Blocking I/O is catastrophic:* if any callback blocks (synchronous file read, synchronous DB query, CPU-intensive loop), the event loop cannot run other callbacks. All in-flight requests are frozen.
- *Complex mental model:* async/await helps but call stacks fragment across callbacks; reasoning about ordering requires care.
- *CPU-bound work:* a CPU-intensive operation on the event loop blocks all other requests for its duration. Offload to a worker thread pool.

**The "async all the way down" requirement:**

An event-loop service is safe only if *every* callsite in the execution path is async. One synchronous library call anywhere in a dependency chain blocks the loop. This is the "red function" problem (Nystrom, 2015): async is contagious — a function that calls an async function must itself be async, propagating up the call stack.

Languages like Go and Java virtual threads (Project Loom) address this by using scheduler-aware blocking: `LockSupport.park()` in a virtual thread yields the underlying OS thread to the scheduler rather than blocking it. This gives the semantic simplicity of thread-per-request with the scalability of event loops.

**Practical concurrency ceiling comparison:**

| Model | Concurrency limit | Memory per concurrent request | Blocking I/O safe? |
|-------|------------------|------------------------------|-------------------|
| Thread-per-request (OS threads) | ~10K threads | 256KB–8MB stack | Yes |
| Thread-per-request (virtual threads) | ~1M | ~1KB heap | Yes |
| Event loop (Node.js, epoll) | ~100K connections | ~1KB state | No — must be async |
| Go goroutines | ~1M | ~2KB stack | Yes (scheduler-aware) |

## Real-world sightings

**Node.js blocking event loop incidents.** Several postmortems describe Node.js services where a CPU-intensive synchronous operation (JSON parsing of a very large payload, regex matching) on the event loop caused all concurrent request handlers to freeze until the operation completed. The symptom: p50 and p99 latency spike together, with a hard spike pattern (requests process normally, then all freeze briefly, then unfreeze simultaneously). Fix: move CPU-intensive work to a Worker thread.

**Java Project Loom (virtual threads).** JDK 21 introduced virtual threads specifically to eliminate the OS-thread-count limit on throughput without requiring async rewrites. A virtual thread that blocks on IO (a socket read, a DB call) parks the virtual thread and releases the underlying OS thread to handle other virtual threads. This lets thread-per-request services scale to millions of concurrent requests without converting code to async.

## Mitigations

### Async I/O throughout the call stack

**What it is:** For event-loop services: use async versions of all I/O libraries. Audit dependencies for synchronous I/O. Use a linter or runtime monitor (e.g., Node.js `--trace-sync-io` flag) to detect accidental synchronous calls.

**Cost:** Async code is harder to write and debug. Async must be used consistently; a single synchronous call anywhere in the dependency chain blocks the loop.

**How it backfires:** Library code or framework internals may have hidden synchronous I/O. Vendored or third-party libraries may not provide async APIs; wrapping them in worker threads adds overhead.

### CPU-bound work offloading

**What it is:** For event-loop services: offload all CPU-intensive operations (image processing, cryptography, serialization of large payloads, parsing) to a separate worker thread pool. Return the result to the event loop via a callback/promise.

**Cost:** Thread pool overhead; cross-thread communication adds latency (usually <1ms for small payloads).

**How it backfires:** If the worker thread pool is saturated, tasks queue. This is now equivalent to blocking I/O from the event loop's perspective — the event loop waits for the worker thread pool, just asynchronously.

### Virtual threads (JVM) or goroutines (Go) for new services

**What it is:** Use a runtime that provides scheduler-aware blocking. Go goroutines and JVM virtual threads block at the scheduler level, not the OS thread level. Thread-per-request code runs unmodified; the scheduler multiplexes thousands of concurrent goroutines/virtual threads onto a small pool of OS threads.

**Cost:** Requires a recent JVM (21+) or Go. Existing Java thread-per-request code works with virtual threads after minimal reconfiguration; existing async Java code does not benefit.

**How it backfires:** Virtual threads and goroutines are not magic — they eliminate OS-thread-count as the bottleneck, but other bottlenecks (CPU, memory bandwidth, connection pool size, mutex contention) remain.

## Interactions

- [Slow Is Worse Than Down](../dependencies/slow-is-worse-than-down.md) — slow dependencies exhaust thread pools in thread-per-request services; in event-loop services, slow async I/O causes response delays without blocking other requests.
- [Staged Architectures](staged-architectures.md) — per-stage thread pools apply the thread-per-request model independently per stage; the stage boundary is where the concurrency model choice is made.
- [Batching](batching.md) — batching is a natural fit for event-loop models (collect callbacks from multiple arriving requests into one batch); harder in thread-per-request without explicit coordination.

## References

- Welsh, M. et al. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." *SOSP 2001*.
  Motivates staged concurrency to address the limitations of both pure thread-per-request and pure event-loop models.
- Nystrom, R. "What Color Is Your Function?" *Journal of Stuffings*, 2015.
  Blog post that concisely explains the async-contagion problem; available at stuffwithstuff.com.
- OpenJDK Project Loom. "Virtual Threads." *JEP 425 / JEP 444*.
  JVM specification and rationale for virtual threads as a solution to the concurrency model tradeoff.
