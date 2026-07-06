# KV Cache Pressure

> **One-liner:** The KV cache for all active sequences must fit in GPU HBM — when it doesn't, the scheduler must preempt sequences and re-run their prefill on readmission, wasting compute on work already done.

## Symptom

- KV memory utilization at 80–95% of GPU HBM; scheduler logs show preemptions.
- TTFT spike for specific requests — these are re-admitted sequences paying re-prefill cost.
- Throughput decreasing despite stable GPU compute utilization (compute is being used on re-prefill instead of new tokens).
- OOM errors from the inference server at extreme load.
- Sequences with long prompts or long partial outputs evicted more frequently (largest KV footprint).

## Mechanism

**KV cache structure:**

Transformers cache key-value tensors from the attention layers to avoid recomputing them for every new token. For a sequence at position `t`, the KV cache holds all prior attention keys and values:

```
KV_bytes(t) = 2 × num_layers × num_heads × head_dim × t × dtype_bytes
```

For a 7B parameter model (fp16, 32 layers, 32 heads × 128 head_dim):
```
KV per token ≈ 2 × 32 × 32 × 128 × 2 = 524 KB per 1000 tokens
```

With GPU HBM of 40 GB and model weights consuming 14 GB:
- Available for KV: ~26 GB
- Maximum active tokens: 26,000 MB / 0.524 MB × 1000 ≈ 49,600 tokens total
- At 100 active sequences with 500-token average length: 26,200 tokens → fits
- At 100 active sequences with 1,000-token average length: 52,400 tokens → OOM

**The fragmentation problem (pre-PagedAttention):**

Early LLM serving systems pre-allocated contiguous memory for each sequence up to `max_tokens`. A sequence with `max_tokens=2048` reserved 2048 × KV_per_token regardless of actual output length. If the sequence generated 200 tokens before finishing, 1848 token-slots were wasted.

Under typical workloads (Kwon et al., 2023 measured real ChatGPT-like request distributions), this fragmentation wastes 60–80% of KV capacity: a 40 GB KV budget effectively becomes a 8–16 GB budget.

**PagedAttention:**

PagedAttention (vLLM) applies the OS page table concept to KV memory. KV cache is divided into fixed-size blocks (pages), typically 16 tokens each. Each sequence is allocated pages on demand; a sequence that generates 200 tokens uses 13 pages (200/16 = 12.5 → 13). A sequence that generates 2,000 tokens uses 125 pages.

Logical-to-physical page mapping allows non-contiguous allocation. Fragmentation is at most one page per sequence (the partially-filled last page). Under typical distributions, effective KV utilization rises from 20–40% to 80–90%.

**Preemption as the memory pressure response:**

When all KV pages are occupied and a new sequence needs to be admitted (or an existing sequence generates more tokens than expected), the scheduler must free pages. Options:
1. *Swap to CPU*: copy evicted sequence's KV pages to CPU RAM, free GPU pages for new work. Restore when the sequence is readmitted.
2. *Recompute (discard KV)*: discard evicted sequence's KV entirely. On readmission, re-run prefill from scratch.
3. *Block admission*: don't admit new sequences until existing ones complete, freeing their pages naturally.

Swapping adds PCIe bandwidth pressure (32 GB/s PCIe 4.0 bandwidth). Recomputing wastes GPU compute (prefill is compute-bound). Blocking reduces throughput during memory pressure.

## Real-world sightings

**Kwon, W. et al. "PagedAttention." (SOSP 2023).** The paper measured KV cache fragmentation on a production ChatGPT-like workload and found that static allocation wastes 60.2% of KV memory on average. PagedAttention recovered this waste and enabled 2–4× higher throughput at identical TTFT and ITL SLOs.

**vLLM production deployment.** vLLM (the open-source serving system built on PagedAttention) is widely deployed for LLM serving. Its GitHub issue tracker documents real-world KV OOM incidents where users underestimate KV footprint at high concurrency, confirming the mechanism described here.

## Mitigations

### PagedAttention (non-contiguous KV allocation)

**What it is:** Allocate KV cache in fixed-size pages rather than contiguous per-sequence slabs. Map non-contiguous physical pages to a logical sequence view using a page table per sequence. Allocate pages on demand as the sequence generates tokens.

**Cost:** Requires modifications to the attention kernel to handle non-contiguous memory access (gather-scatter operations or custom CUDA kernels). Adds one level of indirection per KV access.

**How it backfires:** Page table overhead is small for long sequences (amortized), but non-negligible for very short sequences where page management overhead dominates generation time. Custom attention kernels must be maintained per hardware architecture.

### KV memory budget admission control

**What it is:** Maintain a count of allocated KV pages. Admit a new request only if the estimated KV footprint (prompt_len × KV_per_token + reserve) fits within the remaining budget. Reject or queue new requests when the budget is exhausted.

**Cost:** Requires an estimate of KV footprint at admission, which depends on the unknown output length. The estimate must be pessimistic enough to prevent OOM but not so pessimistic that concurrency drops to zero.

**How it backfires:** A pessimistic estimate (reserve for `max_tokens`) is very conservative. An optimistic estimate (reserve for prompt only) causes OOM when outputs are long, forcing preemption. Most systems use a middle ground (reserve for mean expected output + buffer) and handle edge cases via preemption.

### KV offloading (CPU swap)

**What it is:** When GPU KV memory is under pressure, evict the KV cache for the lowest-priority (or least-recently-used) sequences to CPU RAM. The sequences remain in the active queue; on their next scheduling opportunity, their KV is swapped back from CPU to GPU before the decode step.

**Cost:** CPU ↔ GPU transfer time over PCIe. At PCIe 4.0 bandwidth (~32 GB/s), swapping 1 GB of KV takes ~31ms — acceptable for sequences with low priority or low time-urgency, but significant for latency-sensitive requests.

**How it backfires:** CPU swap bandwidth becomes the bottleneck under high preemption rates. If many sequences are evicted simultaneously, the restore bandwidth queue adds significant latency to their TTFT.

## Interactions

- [Unknown Work Size](unknown-work-size.md) — KV pressure is caused by output length exceeding admission-time estimates; unknown work size is the root cause.
- [Continuous Batching](continuous-batching.md) — continuous batching frees KV pages as sequences complete, reducing sustained memory pressure.
- [Priority and Preemption](priority-and-preemption.md) — KV pressure triggers preemption; priority determines which sequences are evicted.
- [Autoscaling Signals](../capacity/autoscaling-signals.md) — KV cache occupancy (not GPU compute utilization) is the correct autoscaling signal for inference services.

## References

- Kwon, W. et al. "Efficient Memory Management for Large Language Model Serving with PagedAttention." *SOSP 2023*.
  Introduces PagedAttention; measures KV fragmentation at 60–80% in production workloads; shows 2–4× throughput improvement.
- Yu, G. et al. "ORCA: A Distributed Serving System for Transformer-Based Generative Models." *OSDI 2022*.
  Pre-PagedAttention continuous batching; describes KV memory as the primary batching constraint.
