# Cold Starts

> **One-liner:** A new instance at full traffic before its JIT, caches, and connection pools are warm performs worse than an established one — routing it full traffic immediately causes latency spikes that look like overload.

## Symptom

- p99 rises immediately after a deploy or scale-out, before traffic increases further.
- New instances show higher per-request latency than established ones (visible in per-host breakdowns).
- Load balancer reports new backends as healthy but performance is degraded.
- Latency normalizes over 1–5 minutes as the instance warms up.
- Periodic latency spikes that correlate with rolling deploy cadence.

## Mechanism

"Cold start" is an umbrella for several distinct warmup phenomena that each impose a latency cost on the first N requests:

**JIT compilation warmup (JVM, V8, .NET):**

JVM bytecode runs interpreted on first execution; the JIT compiler identifies "hot" code paths (called enough times) and compiles them to native code. Until compilation, each method executes 5–20× slower than its compiled form. In JVM services, the first 1,000–10,000 requests may run at 30–50% of steady-state throughput. The JIT warms up over minutes at production traffic levels.

Observable: CPU higher than steady-state on new instances (interpreter overhead); latency falling monotonically over the first several minutes.

**Connection pool warmup:**

A new instance starts with empty connection pools to its dependencies (database, cache, downstream services). The first requests must establish new connections, paying TCP handshake + TLS + authentication costs per connection. Under a thread-per-request model with a pool of 100 connections, the first 100 requests each pay full connection setup cost; subsequent requests reuse connections.

Observable: Connection setup spans visible in traces for the first N requests; trace waterfall shows TCP/TLS steps for early requests that disappear later.

**Local cache warmup:**

In-process caches (L1 cache, computed results, JIT-compiled templates) are empty at startup. First requests are cold misses; each fetches from downstream (database, distributed cache) and populates the local cache. Hit rate rises over minutes as the working set is loaded.

Observable: Miss rate metric falling over the first several minutes; CPU higher (backend fetches) during the warmup window.

**OS page cache warmup:**

On first memory access, the OS must load the relevant pages into physical memory (a page fault). A JVM with a 2GB heap requires the OS to fault in up to 2GB of pages across startup. Until the working set is paged in, each access may incur a disk read.

Observable: `sar -B` shows high page-fault rate on new instances; latency spikes that decrease as working set fits in RAM.

**Combined effect:** The cumulative warmup effect for a JVM service can cause 2–5× latency for the first few minutes of operation. A service sized correctly for steady-state may appear overloaded immediately after each rolling deploy.

## Real-world sightings

**Netflix "Tips for Reducing JVM Startup Time" (Netflix TechBlog).** Netflix documented JVM warmup causing latency spikes for the first several minutes after each deployment of their API gateway. The post describes pre-warming using synthetic traffic before adding instances to the load balancer. Netflix also implemented class data sharing (JVM CDS) to reduce JIT warmup time.

**AWS Lambda cold starts documentation.** AWS describes Lambda cold starts (first invocation of a new Lambda instance) as adding 100ms–10 seconds of overhead. For Java Lambdas, cold start latency can exceed 5 seconds due to JVM initialization. AWS recommends provisioned concurrency (pre-warmed instances) for latency-sensitive Lambda functions.

## Mitigations

### Traffic ramp (slow start)

**What it is:** When a new instance joins the load balancer pool, start it at low routing weight (1–5% of normal traffic). Increase the weight gradually over a warmup window (30–120 seconds). By the time it reaches full weight, JIT, connection pools, and caches are warm.

**Cost:** New capacity not fully available immediately; extends the effective scale-up lag. Requires load balancer support for per-instance routing weights.

**How it backfires:** Under an urgent scale-out to handle a traffic spike, slow ramp delays when the new capacity is useful. The ramp window must be calibrated to the warmup duration; too short defeats the purpose.

### Synthetic warm-up before LB registration

**What it is:** Send a controlled stream of synthetic requests to the new instance *before* registering it in the load balancer pool. The synthetic traffic exercises hot code paths, fills connection pools, and populates local caches. Only after the warmup completes (or after hit rate and latency stabilize) is the instance added to the pool.

**Cost:** Requires a warmup harness that generates realistic-enough traffic to cover hot code paths. Idempotent operations are easy; writes require care to avoid side effects.

**How it backfires:** Synthetic traffic that doesn't match the production request mix warms some paths but leaves others cold. A warmup harness based on last week's access logs may miss seasonally or event-driven traffic patterns.

### JVM class data sharing and AOT compilation

**What it is:** Use JVM Class Data Sharing (CDS) or ahead-of-time (AOT) compilation (GraalVM native image, Quarkus) to eliminate or reduce JIT warmup time. CDS pre-loads parsed class metadata; native image compiles the application to machine code at build time, eliminating the interpreter entirely.

**Cost:** AOT compilation (native image) significantly complicates the build process and may require changes to reflection-heavy code. CDS is easier but provides only partial warmup reduction.

**How it backfires:** Native-image compilation fixes the compiled code at build time; JIT's adaptive optimization (re-compiling based on runtime profile) is not available. Some workloads perform worse with AOT than with JIT after warmup.

## Interactions

- [Scale-Up Lag](scale-up-lag.md) — warmup lag is the third component of total scale-up lag; cold starts lengthen the window between scale-out trigger and useful new capacity.
- [Cold Restart Warmup](../caching/cold-restart-warmup.md) — the cache-specific cold start: origin overload during cache warmup.
- [Health Checking](../load-balancing/health-checking.md) — health checks should gate on actual request latency, not just process liveness, to prevent unhealthy-but-live cold instances from receiving production traffic prematurely.

## References

- Amazon Web Services. "AWS Lambda cold starts." *AWS Documentation*.
  Quantifies cold start latency by runtime; describes provisioned concurrency as mitigation.
- Evans, B. and Gough, J. *Optimizing Java*. O'Reilly, 2018.
  Chapters 9–11 cover JIT compilation and its warmup behavior; the warmup curve description derives from this work.
