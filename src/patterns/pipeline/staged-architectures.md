# Staged Architectures

> **One-liner:** Breaking a pipeline into stages with per-stage queues allows each stage to operate at its own rate — but requires explicit backpressure or the slowest stage's queue grows without bound.

## Symptom

- One pipeline stage CPU-pegged or memory-bound; others idle.
- Queue depth growing between the slow stage and its upstream.
- End-to-end latency dominated by queueing time, not processing time.
- Memory growing on the stage that receives work faster than it can process it.
- Cascading slowdown: upstream stage backs up when downstream queue is full.

## Mechanism

**Why unified thread pools break under mixed workloads:**

A traditional server handles requests with a single thread pool. One handler does: receive → validate → fetch from DB → render → serialize → send. All of these steps share the same pool. A slow DB fetch (step 3) holds a thread from step 1 through step 6, blocking other requests from being received or validated.

SEDA (Staged Event-Driven Architecture, Welsh et al., 2001) decomposes this pipeline into discrete stages:
```
[receive] → queue₁ → [validate] → queue₂ → [fetch] → queue₃ → [render] → queue₄ → [send]
```

Each stage has its own thread pool, sized for that stage's bottleneck. Stage 3 (fetch) might need 200 threads (IO-bound, waiting on DB); stage 4 (render) might need 8 threads (CPU-bound). The queues between stages decouple their execution: stage 2 runs at full speed even if stage 3 is slow.

**Throughput calculation for staged pipelines:**

By Little's Law applied to each stage independently, a stage at service rate μᵢ with queue depth Lᵢ has wait time Wᵢ = Lᵢ/μᵢ. End-to-end latency is the sum of per-stage latency: W_total = Σ Wᵢ. When one stage is the bottleneck (lowest μᵢ), its queue grows without bound unless either:
1. The upstream stages are rate-limited (backpressure), or
2. Items are dropped from the bottleneck queue (load shedding).

**The unbounded queue failure mode:**

Without backpressure, inter-stage queues accumulate all excess load. A 10ms spike in stage 3 latency (due to a slow DB response) allows 100 requests/second × 10ms = 1 item of additional queue depth — harmless. But a sustained 10% throughput reduction at stage 3 causes queues to grow linearly at 10 items/second indefinitely, until memory is exhausted or the process OOMs.

**Bounded queues and the deadlock trap:**

Making queues bounded solves the memory problem but introduces a deadlock risk. If stage A and stage B share a thread pool, and stage A's queue is full and stage A's handler is blocking (waiting to enqueue into stage B's queue), while stage B's handler also blocks on stage A's queue — deadlock. The fix: each stage must have an independent thread pool, or queues must shed rather than block.

## Real-world sightings

**Welsh, M. et al. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." (SOSP 2001).** The original SEDA paper introduces staged architectures specifically to address the shared-pool HOL blocking problem. The paper presents Haboob, a Java web server built on SEDA stages, and shows that per-stage bounded queues with backpressure sustain higher goodput under overload than a shared-pool design. The paper also introduces the term "well-conditioned" to describe a service that gracefully degrades (maintains throughput while shedding some load) rather than collapsing under overload.

**Kafka streams topology.** Apache Kafka Streams decomposes stream processing into a DAG of processing nodes, each consuming from and producing to Kafka topics. The Kafka topic between nodes acts as the inter-stage bounded queue with durable storage. Backpressure is implicit: a slow consumer causes the producer to accumulate consumer lag (offset gap); Kafka's consumer group protocol allows rebalancing but does not create back-pressure to the producer. Explicit back-pressure requires producer rate limiting.

## Mitigations

### Per-stage bounded queues with backpressure

**What it is:** Cap each inter-stage queue at a maximum size. When a downstream queue is full, the upstream stage signals backpressure: either block (don't accept new items until space is available) or shed (drop items or return 503). The upstream stage must have a way to propagate this signal further upstream.

**Cost:** Requires the upstream stage to handle blocking or rejection. Blocking can stall the upstream stage's thread pool; rejection requires the caller to handle errors.

**How it backfires:** Blocking the upstream stage on a full downstream queue deadlocks if the same thread pool handles both stages. Always use separate pools per stage, or use async non-blocking puts with explicit shed-on-full policy.

### Per-stage thread pool sizing

**What it is:** Size each stage's thread pool independently based on its bottleneck resource. IO-bound stages (waiting on network) get large pools (50–200 threads); CPU-bound stages get pools sized to core count. This ensures that a slow IO stage doesn't starve a fast CPU stage of threads.

**Cost:** More threads overall; requires understanding each stage's resource profile.

**How it backfires:** If a stage's bottleneck shifts (e.g., a usually fast DB becomes slow), its thread pool may be too small. Monitor per-stage queue depth and latency separately; alert when a stage's queue depth grows.

### Work stealing across stages

**What it is:** Allow threads from less-busy stages to pick up work from busier stages when they are idle. Requires a work-stealing scheduler (e.g., Java's ForkJoinPool) or explicit cross-stage thread lending.

**Cost:** Complicates per-stage isolation; a stage that "steals" from another may miss its own queue filling up.

**How it backfires:** Work stealing is useful for CPU-bound stages where the bottleneck is cores. For IO-bound stages, the bottleneck is connections/file descriptors, not thread count; work stealing doesn't help.

## Interactions

- [Backpressure](../overload/backpressure.md) — the mechanism that prevents queue unbounded growth in staged architectures; SEDA backpressure is the pipeline-specific application.
- [Mixed Request Patterns](../multitenancy/mixed-request-patterns.md) — per-stage pools isolate request classes within each stage; mixed size classes within one stage still need size-class pooling.
- [Batching](batching.md) — batching between stages reduces inter-stage communication overhead.
- [Concurrency Models](concurrency-models.md) — event-loop vs. thread-per-request is the per-stage concurrency model decision.

## References

- Welsh, M., Culler, D., and Brewer, E. "SEDA: An Architecture for Well-Conditioned, Scalable Internet Services." *SOSP 2001*.
  The foundational staged architecture paper; introduces per-stage queues, backpressure, and the "well-conditioned" service concept.
- Ousterhout, J. "Why Threads Are a Bad Idea (for most purposes)." *USENIX ATC 1996*.
  Motivates why thread-per-stage is still better than the alternative (a single thread for the whole pipeline); provides context for the SEDA design choices.
