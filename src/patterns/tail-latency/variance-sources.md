# Variance Sources

> **One-liner:** p99 spikes that aren't explained by load or downstream latency usually trace to one of a small set of within-process variance sources: GC, page faults, thermal throttling, or connection churn.

## Symptom

- p99 high and p50 stable — no load increase or dependency change to explain it.
- Variance appears periodic: every N seconds, the p99 spikes, then recovers. (GC pause frequency is a function of allocation rate and heap size.)
- Variance correlated with specific hosts, not all hosts simultaneously. (GC tune may differ; host temperature differs; page cache state differs.)
- Slow requests don't correlate with request type, tenant, or payload size — variance is distributed across all request types uniformly.
- Profiling shows the slow tail is not in application code but in JVM/OS-level operations.

## Mechanism

These are the dominant within-process variance sources at p99:

**GC pauses (JVM, .NET, Go):**

Stop-the-world (STW) GC events pause all application threads for the duration of the GC cycle. G1GC and ZGC reduce STW pause length to tens of milliseconds for most cycles, but full GC (triggered when G1GC can't keep up) can cause multi-second pauses. In Go, GC is concurrent but introduces STW pauses for stack scanning — typically < 1ms, but non-zero.

*Observable:* JVM GC logs; prometheus `jvm_gc_pause_seconds`; Go `GODEBUG=gctrace=1`. Pause times appear as vertical lines on latency heatmaps at the GC frequency.

*Key variables:* Allocation rate (higher → GC more frequent), live heap size (larger → GC longer), old-gen fragmentation (higher → GC more disruptive), GC algorithm choice.

*Mitigation direction:* Reduce allocation rate (reuse objects, use buffers), tune heap size (larger heap = less frequent GC at the cost of longer pauses when they occur), switch to low-latency GC (ZGC, Shenandoah for JVM).

**Page faults:**

The operating system's page cache stores recently-used memory-mapped files and anonymous memory. On first access to a memory page not in the cache, the OS must fetch it from disk (a "major" page fault): this takes 1–100ms depending on disk latency.

Sources: freshly deployed binaries (the OS hasn't loaded the binary's pages yet); memory-mapped database files accessed after a restart; large heap allocations that touch previously unused virtual memory.

*Observable:* `perf stat -e page-faults` or `/proc/<pid>/status VmRSS vs VmVirt`; large gap between virtual and resident memory indicates pages that will fault on first access.

*Mitigation direction:* Pre-fault memory at startup (`madvise(MADV_WILLNEED)`, `mlockall`); pre-load shared libraries before receiving traffic; use a shared memory cache that survives restarts (process-local page cache persists).

**Thermal throttling:**

Modern CPUs reduce clock speed when junction temperature exceeds safe limits. In cloud VMs running on shared physical hosts, neighboring tenants' CPU-intensive workloads heat the host CPU, causing throttling on all VMs on that host — including yours. Thermal events are not visible from inside the VM.

*Observable:* CPU frequency sensors (`cpufreq`), `perf stat -e cpu-cycles,task-clock` (if ratio drops, clock speed dropped), correlation between latency spikes and neighbor workloads (hard to see from inside a VM). Cloud providers may expose throttling metrics.

*Mitigation direction:* Spread instances across host families to reduce correlated thermal events; use dedicated tenancy (bare metal) for latency-sensitive workloads; avoid CPU-intensive co-tenants.

**Connection churn:**

Establishing a new TCP connection involves: TCP 3-way handshake (~0.5 × RTT), TLS handshake (1–2 RTTs), authentication (1 RTT per layer), connection pool initialization. Total cost: 10–200ms depending on RTT and auth depth.

When connections are not kept warm (pool too small, idle timeout too short, upstream keepalive mismatch), requests trigger new connection setup, adding the full setup cost to their latency. Under load spikes that exceed pool size, many requests simultaneously establish connections — a "connection storm."

*Observable:* Trace spans for connection setup; connection pool metrics (pool hit rate); `netstat` showing TIME_WAIT accumulation (connections being closed and re-established).

*Mitigation direction:* Pre-warm connection pools at service start; set pool size ≥ expected peak concurrency; match idle timeout to upstream keepalive; use HTTP/2 or gRPC (multiplexed connections avoid per-request connection overhead).

## Real-world sightings

**Dean, J. and Barroso, L.A., "The Tail at Scale" (CACM 2013).** Section 2 catalogs variance sources at Google, noting that GC events, page cache misses, network switches temporarily buffering packets, and scheduled background tasks are all consistent sources of tail latency spikes in warehouse-scale computing. The paper treats these as unavoidable and argues that the response is architecture (hedging, cancellation) rather than elimination.

**Netflix, "Application GC Pauses and How to Avoid Them."** Netflix Engineering Blog describes how GC pauses in JVM services correlated with p99 spikes on customer-facing APIs. The post traces specific GC algorithms (G1GC vs. CMS) and their pause characteristics, and reports that migrating to G1GC with tuned region sizes reduced p99 spikes by 40%.

## Mitigations

### GC tuning and allocation reduction

**What it is:** Profile allocation rate (bytes/second allocated); identify the highest-allocation code paths; reduce per-request object creation by reusing buffers, using object pools, or switching to off-heap data structures. Tune GC algorithm parameters for the target pause time (e.g., `-XX:MaxGCPauseMillis=50` for G1GC).

**Cost:** Profiling and tuning is time-consuming; reduced allocation often requires significant code changes.

**How it backfires:** Reducing max GC pause time by tuning (`-XX:MaxGCPauseMillis=10`) causes the GC to run more frequently to meet the target, increasing overall GC CPU overhead. Reducing heap size to reduce pause duration causes more frequent GC at the same allocation rate.

### Connection pooling and keepalives

**What it is:** Maintain a warm pool of connections to each downstream at minimum-pool-size connections, even when idle. Set idle timeout to be longer than the upstream's keepalive timeout. Size the pool to peak expected concurrency: N ≥ RPS × mean_latency (Little's Law).

**Cost:** Idle connections consume file descriptors, kernel TCP state, and memory on both client and server.

**How it backfires:** Pool too large → upstream runs out of connections (file descriptor exhaustion, max connection limit). Pool too small → requests encounter connection setup latency under load spikes. Idle timeout too short relative to upstream keepalive → connections close mid-request under low load, causing setup overhead when load resumes.

### Heap pre-faulting and binary pre-warming

**What it is:** Before directing traffic to a new instance, pre-fault the JVM heap and pre-load the binary by executing a warm-up workload (synthetic requests or replay of real traffic). The OS loads binary pages into the page cache and the JVM populates its heap during this window; subsequent requests don't trigger faults.

**Cost:** Adds latency to instance startup; requires a warm-up workload that exercises the full code path.

**How it backfires:** Warm-up workload may not cover all code paths. Infrequently-called code paths (error handlers, rare request types) will still fault on first production invocation.

## Interactions

- [Hedged Requests](hedged-requests.md) — hedging is effective against stochastic variance (GC pauses, page faults) but not against systemic or process-wide variance sources.
- [Fanout Amplification](fanout-amplification.md) — GC spikes at 1% probability amplify dramatically with fan width; fanout amplifies all per-shard variance sources.
- [Cold Restart Warmup](../caching/cold-restart-warmup.md) — page faults and connection setup are the within-process causes of post-restart latency spikes.

## References

- Dean, J. and Barroso, L.A. "The Tail at Scale." *Communications of the ACM* 56(2), 2013.
  Section 2 catalogs variance sources in production; Section 3 describes mitigations at the architectural level.
- Titzer, B. et al. "V8: An open source JavaScript engine." *Google*, 2008.
  (And later GC papers from the V8 and HotSpot teams) — background on GC algorithm tradeoffs.
- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  Chapter 10 covers variance in service time distributions and its effect on queue waiting time (variance amplification).
