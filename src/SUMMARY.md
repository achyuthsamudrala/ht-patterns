# Summary

[Introduction](introduction.md)
[Symptom Index](symptom-index.md)
[Interaction Map](interaction-map.md)

---

# Foundations

- [Little's Law](foundations/littles-law.md)
- [Latency Percentiles](foundations/latency-percentiles.md)
- [Open vs. Closed Loop](foundations/open-vs-closed-loop.md)
- [Goodput vs. Throughput](foundations/goodput-vs-throughput.md)

---

# Patterns

- [Overload](patterns/overload/index.md)
  - [Goodput Collapse](patterns/overload/goodput-collapse.md)
  - [Load Shedding](patterns/overload/load-shedding.md)
  - [Retry Storms](patterns/overload/retry-storms.md)
  - [Backpressure](patterns/overload/backpressure.md)
  - [Queue Management](patterns/overload/queue-management.md)
  - [Deadline Propagation](patterns/overload/deadline-propagation.md)
  - [Adaptive Concurrency](patterns/overload/adaptive-concurrency.md)
  - [Metastable Failures](patterns/overload/metastable-failures.md)

- [Capacity](patterns/capacity/index.md)
  - [Autoscaling Signals](patterns/capacity/autoscaling-signals.md)
  - [Scale-Up Lag](patterns/capacity/scale-up-lag.md)
  - [Cold Starts](patterns/capacity/cold-starts.md)
  - [Scale-Down Safety](patterns/capacity/scale-down-safety.md)
  - [Static Stability](patterns/capacity/static-stability.md)

- [Multitenancy](patterns/multitenancy/index.md)
  - [Cost-Aware Quotas](patterns/multitenancy/cost-aware-quotas.md)
  - [Fair Scheduling](patterns/multitenancy/fair-scheduling.md)
  - [Mixed Request Patterns](patterns/multitenancy/mixed-request-patterns.md)
  - [Shuffle Sharding](patterns/multitenancy/shuffle-sharding.md)

- [Tail Latency](patterns/tail-latency/index.md)
  - [Fanout Amplification](patterns/tail-latency/fanout-amplification.md)
  - [Hedged Requests](patterns/tail-latency/hedged-requests.md)
  - [Slow Request Isolation](patterns/tail-latency/slow-request-isolation.md)
  - [Variance Sources](patterns/tail-latency/variance-sources.md)

- [Caching](patterns/caching/index.md)
  - [Cache as Hard Dependency](patterns/caching/cache-as-hard-dependency.md)
  - [Stampede and Coalescing](patterns/caching/stampede-and-coalescing.md)
  - [Leases](patterns/caching/leases.md)
  - [Slow Cache vs. Down Cache](patterns/caching/slow-cache-vs-down-cache.md)
  - [Hot Keys](patterns/caching/hot-keys.md)
  - [Cold Restart Warmup](patterns/caching/cold-restart-warmup.md)

- [Dependencies](patterns/dependencies/index.md)
  - [Slow Is Worse Than Down](patterns/dependencies/slow-is-worse-than-down.md)
  - [Bulkheads](patterns/dependencies/bulkheads.md)
  - [Degradation Ladders](patterns/dependencies/degradation-ladders.md)
  - [Criticality Tiers](patterns/dependencies/criticality-tiers.md)
  - [Correlated Failure](patterns/dependencies/correlated-failure.md)

- [Databases](patterns/databases/index.md)
  - [Replication Lag](patterns/databases/replication-lag.md)
  - [Read/Write Splitting](patterns/databases/read-write-splitting.md)
  - [Lock Contention and Deadlocks](patterns/databases/lock-contention-and-deadlocks.md)
  - [Optimistic Concurrency Control](patterns/databases/optimistic-concurrency-control.md)
  - [Write Skew and Read/Write Conflicts](patterns/databases/write-skew-and-read-write-conflicts.md)
  - [Connection Pool Exhaustion](patterns/databases/connection-pool-exhaustion.md)
  - [Hot Partitions and Sequential Keys](patterns/databases/hot-partitions-and-sequential-keys.md)
  - [Failover and Split-Brain](patterns/databases/failover-and-split-brain.md)

- [Pipeline](patterns/pipeline/index.md)
  - [Staged Architectures](patterns/pipeline/staged-architectures.md)
  - [Concurrency Models](patterns/pipeline/concurrency-models.md)
  - [Batching](patterns/pipeline/batching.md)
  - [Queue Sizing](patterns/pipeline/queue-sizing.md)

- [Load Balancing](patterns/load-balancing/index.md)
  - [Algorithms Under Stress](patterns/load-balancing/algorithms-under-stress.md)
  - [Consistent Hashing](patterns/load-balancing/consistent-hashing.md)
  - [Health Checking](patterns/load-balancing/health-checking.md)
  - [Connection Management](patterns/load-balancing/connection-management.md)

- [Inference](patterns/inference/index.md)
  - [Unknown Work Size](patterns/inference/unknown-work-size.md)
  - [Continuous Batching](patterns/inference/continuous-batching.md)
  - [KV Cache Pressure](patterns/inference/kv-cache-pressure.md)
  - [Prefill vs. Decode](patterns/inference/prefill-vs-decode.md)
  - [Token-Level SLOs](patterns/inference/token-level-slos.md)
  - [Prefix Caching](patterns/inference/prefix-caching.md)
  - [Priority and Preemption](patterns/inference/priority-and-preemption.md)
  - [Inference Cold Starts](patterns/inference/inference-cold-starts.md)

---

[References](references.md)
