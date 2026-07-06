# Symptom Index

The incident-mode entry point. Find your observable below, then follow the discriminators to the most likely candidate patterns.

---

## Latency

### p99 exploded, p50 is fine

- CPU is also pegged → [Goodput Collapse](patterns/overload/goodput-collapse.md)
- CPU is low, queue depth rising → [Queue Management](patterns/overload/queue-management.md) or [Backpressure](patterns/overload/backpressure.md)
- New deploys or restarts preceded it → [Cold Starts](patterns/capacity/cold-starts.md) or [Cold Restart Warmup](patterns/caching/cold-restart-warmup.md)
- Fanout service, shards look healthy individually → [Fanout Amplification](patterns/tail-latency/fanout-amplification.md)
- Specific slow host(s) → [Variance Sources](patterns/tail-latency/variance-sources.md) or [Health Checking](patterns/load-balancing/health-checking.md)
- Small requests slow, large requests fine → [Mixed Request Patterns](patterns/multitenancy/mixed-request-patterns.md) or [Slow Request Isolation](patterns/tail-latency/slow-request-isolation.md)

### All percentiles rising together

- Load is increasing proportionally → [Goodput Collapse](patterns/overload/goodput-collapse.md) or [Scale-Up Lag](patterns/capacity/scale-up-lag.md)
- Load is flat, latency crept up over hours → [Queue Management](patterns/overload/queue-management.md) (unbounded queue filling)
- Dependency latency increased → [Slow Is Worse Than Down](patterns/dependencies/slow-is-worse-than-down.md)
- Queue depth high and growing → [Queue Sizing](patterns/pipeline/queue-sizing.md)

### Latency rises after deploy or scale-up

- Scale-up: new instances are slow → [Cold Starts](patterns/capacity/cold-starts.md)
- Cache-backed service, new instances have empty caches → [Cold Restart Warmup](patterns/caching/cold-restart-warmup.md)
- New code: connections or pools are exhausting → [Connection Management](patterns/load-balancing/connection-management.md)
- Rolling deploy: p99 spikes during each wave → [Cold Starts](patterns/capacity/cold-starts.md) (JIT warmup per instance)

### Latency spikes periodically on a regular cadence

- Autoscaler scaling down and cold-starting → [Scale-Down Safety](patterns/capacity/scale-down-safety.md)
- GC pauses or OS page faults → [Variance Sources](patterns/tail-latency/variance-sources.md)
- Connection pool churn on a regular interval → [Connection Management](patterns/load-balancing/connection-management.md)

### TTFT fine, tokens-per-second degrading

*Inference-specific*

- Memory pressure on GPU → [KV Cache Pressure](patterns/inference/kv-cache-pressure.md)
- Batch fill rate low → [Continuous Batching](patterns/inference/continuous-batching.md)
- Decode competing with prefill on same host → [Prefill vs. Decode](patterns/inference/prefill-vs-decode.md)
- Preemptions visible in scheduler logs → [Priority and Preemption](patterns/inference/priority-and-preemption.md)

### TTFT high even at low load

*Inference-specific*

- Model weights still loading (new instance) → [Inference Cold Starts](patterns/inference/inference-cold-starts.md)
- Request queued behind large decode batch → [Continuous Batching](patterns/inference/continuous-batching.md)
- Prefill host pool undersized → [Prefill vs. Decode](patterns/inference/prefill-vs-decode.md)

---

## Throughput

### Accepted QPS up, completed-within-SLO QPS down

- Server-side error rate increasing → [Goodput Collapse](patterns/overload/goodput-collapse.md)
- Timeouts expiring before completion → [Deadline Propagation](patterns/overload/deadline-propagation.md)
- Output token counts growing → [Token-Level SLOs](patterns/inference/token-level-slos.md)

### Throughput plateaued below provisioned capacity

- IO-bound workload, CPU looks fine → [Autoscaling Signals](patterns/capacity/autoscaling-signals.md) (wrong signal)
- Large requests blocking small ones → [Mixed Request Patterns](patterns/multitenancy/mixed-request-patterns.md)
- Concurrency limit hit → [Adaptive Concurrency](patterns/overload/adaptive-concurrency.md)
- Queue backing up between pipeline stages → [Staged Architectures](patterns/pipeline/staged-architectures.md)

### Throughput collapses and doesn't recover after the spike

- Error rate stays elevated after load drops → [Metastable Failures](patterns/overload/metastable-failures.md)
- Retry rate high → [Retry Storms](patterns/overload/retry-storms.md)
- Cache hit rate low after restart → [Cold Restart Warmup](patterns/caching/cold-restart-warmup.md)

### GPU throughput lower than model specs suggest

*Inference-specific*

- Static batching in use, high output-length variance → [Continuous Batching](patterns/inference/continuous-batching.md)
- KV cache fragmentation wasting HBM → [KV Cache Pressure](patterns/inference/kv-cache-pressure.md)
- Prefix not being reused across requests → [Prefix Caching](patterns/inference/prefix-caching.md)

---

## Errors

### Timeout errors without server-side errors

- Client timeout shorter than server processing time → [Deadline Propagation](patterns/overload/deadline-propagation.md)
- Slow upstream dependency → [Slow Is Worse Than Down](patterns/dependencies/slow-is-worse-than-down.md)
- Connection pool exhaustion → [Connection Management](patterns/load-balancing/connection-management.md)

### Error rate oscillates

- Retry bursts driving oscillation → [Retry Storms](patterns/overload/retry-storms.md)
- Autoscaler thrashing → [Scale-Down Safety](patterns/capacity/scale-down-safety.md)
- LB health check cycling ejecting/readmitting hosts → [Health Checking](patterns/load-balancing/health-checking.md)

### One tenant or route erroring, rest healthy

- Quota exhaustion → [Cost-Aware Quotas](patterns/multitenancy/cost-aware-quotas.md)
- Hot key on a shared cache shard → [Hot Keys](patterns/caching/hot-keys.md)
- Tenant blast radius not contained → [Shuffle Sharding](patterns/multitenancy/shuffle-sharding.md) or [Bulkheads](patterns/dependencies/bulkheads.md)
- One tenant's long requests blocking others' short ones → [Fair Scheduling](patterns/multitenancy/fair-scheduling.md)

### Errors spike when a new instance joins

- Instance not yet warmed, receiving full traffic → [Cold Starts](patterns/capacity/cold-starts.md)
- Connection storm from all clients connecting simultaneously → [Connection Management](patterns/load-balancing/connection-management.md)

### Error spike correlates with scale-in event

- In-flight requests dropped during scale-down → [Scale-Down Safety](patterns/capacity/scale-down-safety.md)
- Instance removed from LB without draining → [Scale-Down Safety](patterns/capacity/scale-down-safety.md)

---

## Resource

### Memory climbing under steady load

- Unbounded work queue → [Queue Management](patterns/overload/queue-management.md) or [Queue Sizing](patterns/pipeline/queue-sizing.md)
- KV cache not being evicted → [KV Cache Pressure](patterns/inference/kv-cache-pressure.md)
- Connection objects accumulating → [Connection Management](patterns/load-balancing/connection-management.md)

### CPU low but service saturated

- IO-bound workload with thread-per-request model → [Concurrency Models](patterns/pipeline/concurrency-models.md)
- Downstream dependency slow → [Slow Is Worse Than Down](patterns/dependencies/slow-is-worse-than-down.md)
- Lock contention → [Variance Sources](patterns/tail-latency/variance-sources.md)

### GPU utilization low but requests queueing

*Inference-specific*

- Batch size too small → [Continuous Batching](patterns/inference/continuous-batching.md) or [Batching](patterns/pipeline/batching.md)
- Prefill phase blocking decode → [Prefill vs. Decode](patterns/inference/prefill-vs-decode.md)
- Routing not accounting for prefix locality → [Prefix Caching](patterns/inference/prefix-caching.md)

### GPU OOM / HBM exhausted

*Inference-specific*

- Too many concurrent long sequences → [KV Cache Pressure](patterns/inference/kv-cache-pressure.md)
- Unknown output length exceeding reservation → [Unknown Work Size](patterns/inference/unknown-work-size.md)
- KV fragmentation under static allocation → [KV Cache Pressure](patterns/inference/kv-cache-pressure.md) (PagedAttention)

### Autoscaling not responding to obvious overload

- Wrong signal (CPU for IO-bound service) → [Autoscaling Signals](patterns/capacity/autoscaling-signals.md)
- Scale-down cooldown still active → [Scale-Down Safety](patterns/capacity/scale-down-safety.md)
- Control plane partitioned → [Static Stability](patterns/capacity/static-stability.md)

---

## Recovery

### Restarts make it worse

- Cache lost on restart, backends now overloaded → [Cache as Hard Dependency](patterns/caching/cache-as-hard-dependency.md)
- Retries amplifying load on restarting nodes → [Retry Storms](patterns/overload/retry-storms.md)
- New instances cold, LB sending full traffic → [Cold Starts](patterns/capacity/cold-starts.md)

### It stayed broken after the trigger cleared

- Self-sustaining feedback loop → [Metastable Failures](patterns/overload/metastable-failures.md)
- Queue still draining work from the overload window → [Queue Management](patterns/overload/queue-management.md) or [Queue Sizing](patterns/pipeline/queue-sizing.md)
- Correlated dependency still degraded → [Correlated Failure](patterns/dependencies/correlated-failure.md)

### Degradation mode won't clear without manual intervention

- All degradation levels active, no automatic recovery → [Degradation Ladders](patterns/dependencies/degradation-ladders.md)
- Control plane failure preventing automatic remediation → [Static Stability](patterns/capacity/static-stability.md)
- Metastable state requiring external load reduction → [Metastable Failures](patterns/overload/metastable-failures.md)
