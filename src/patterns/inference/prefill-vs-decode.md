# Prefill vs. Decode

> **One-liner:** Prefill is compute-bound; decode is memory-bandwidth-bound — running both on the same GPU forces each phase to idle its respective bottleneck resource, and a long prefill stalls decode for every co-located sequence until it finishes.

## Symptom

- TTFT correlating with current decode batch size (prefill is queued behind running decode steps).
- ITL spikes whenever a large prefill request is admitted — decode stalls for all active streams during prefill.
- GPU compute utilization looks high but one dimension is wasted: compute idle during decode, memory bandwidth idle during prefill.
- Large prompts causing visible stutter in streaming output for other active users.

## Mechanism

**The two-phase computation model:**

Autoregressive token generation has two computationally distinct phases:

*Prefill:* Process the entire input prompt in one forward pass. All prompt tokens are processed in parallel — this is matrix-matrix multiplication (high arithmetic intensity). The GPU's compute units are fully utilized; memory bandwidth utilization is moderate.

*Decode:* Generate one new token per forward pass. Each decode step is a matrix-vector multiplication (one token attending to all KV cache entries). Arithmetic intensity is very low — the GPU loads the full model weights and KV cache from HBM for each token, performing very little arithmetic relative to the data transferred. Memory bandwidth is the binding constraint; compute units are mostly idle.

**The mismatch on shared hardware:**

A GPU optimized for throughput (H100, A100) has high compute throughput and high HBM bandwidth, but they serve different bottlenecks:

| Phase | Bottleneck | Compute utilization | Memory BW utilization |
|-------|-----------|---------------------|----------------------|
| Prefill | Compute (FLOPS) | High (70–90%) | Moderate (30–50%) |
| Decode | Memory bandwidth | Low (5–15%) | High (70–90%) |

Running both on the same GPU means during prefill: memory BW idles at 30–50%. During decode: compute idles at 5–15%. Neither phase fully utilizes the GPU.

**Prefill-decode serialization:**

When a new request is admitted into a continuous batching system, its prefill must complete before it can join the decode batch. During prefill, the GPU runs a large matrix-matrix multiply for the prompt. This blocks all ongoing decode steps for active sequences — their decode is paused while prefill runs.

For a 4,000-token prompt at 0.1ms/token: prefill takes ~400ms. All active sequences experience a 400ms ITL gap. For an ITL SLO of 50ms, this is an 8× violation for all concurrent users.

**Disaggregation (DistServe, Splitwise):**

The observation that prefill and decode have orthogonal hardware requirements leads to disaggregation: run prefill on dedicated "prefill hosts" sized for compute throughput, and decode on dedicated "decode hosts" sized for memory bandwidth.

Workflow:
1. Request arrives at a gateway; prompt is routed to a prefill host.
2. Prefill host runs the full prompt forward pass; generates the first token and the KV cache.
3. KV cache is transferred from prefill host to an assigned decode host (via NVLink, InfiniBand, or PCIe).
4. Decode host begins generating subsequent tokens.

This eliminates prefill-decode interference: decode hosts never stall for prefill; prefill hosts batch large prompts at full compute efficiency.

## Real-world sightings

**Zhong et al. "DistServe" (OSDI 2024).** The paper provides the clearest empirical evidence for prefill-decode heterogeneity. It measures that, on Llama-2-13B, satisfying a TTFT ≤ 2s SLO requires 4× the compute throughput that satisfying ITL ≤ 100ms requires — their optimal hardware configurations for each phase use entirely different GPU-to-memory-bandwidth ratios. The paper shows 2–3.8× goodput improvement from disaggregation vs. co-located serving.

**Patel et al. "Splitwise" (ISCA 2024).** Independent analysis from the computer architecture perspective, studying the prefill/decode hardware profile on A100 and H100. Splitwise demonstrates that mixed-phase workloads leave 40–60% of GPU compute idle during decode-heavy periods, motivating hardware-level disaggregation.

## Mitigations

### Chunked prefill (interleaving on shared hardware)

**What it is:** Split each request's prefill into chunks of C tokens. Process one chunk per iteration, interleaved with the regular decode step for active sequences. This prevents any single prefill from causing an unbounded ITL gap.

ITL impact per iteration = C × prefill_ms_per_token (instead of full_prompt_length × prefill_ms_per_token).

**Cost:** Adds per-chunk scheduling overhead. Longer total time-to-first-token for the new request (its prefill is spread over multiple iterations instead of completed in one). Chunk size C must be tuned to balance ITL impact with prefill completion time.

**How it backfires:** For very long prompts (10K+ tokens), even chunked prefill adds many decode-step delays for active sequences. At chunk size C=256 tokens and 10K-token prompt: 40 iterations of delay for active sequences; at 20ms/iteration, that's 800ms of additional ITL spread over several seconds.

### Prefill-decode disaggregation (separate host pools)

**What it is:** Deploy separate pools of GPUs for prefill and decode. Route incoming requests to a prefill host for prompt processing; transfer the resulting KV cache to a decode host for token generation. Each host pool is independently sized:
- Prefill hosts: fewer GPUs with high FLOP throughput; large prefill batches.
- Decode hosts: more GPUs (decode is throughput-limited); smaller batches with high KV bandwidth.

**Cost:** KV cache transfer latency adds to TTFT. For a 2,000-token prompt at 0.524 MB/1000 tokens: KV cache = 1.05 GB. At 200 GB/s NVLink: ~5ms transfer. For requests where TTFT ≤ 100ms is required, 5ms is acceptable; for ≤ 20ms TTFT requirements, disaggregation may not help.

**How it backfires:** Short-prompt, short-output requests may not benefit: the disaggregation overhead (routing, transfer, decode host assignment) can exceed the elimination of prefill-decode interference. Disaggregation is most beneficial for long-context or long-output workloads.

## Interactions

- [Continuous Batching](continuous-batching.md) — chunked prefill extends continuous batching to control prefill-decode interference within a shared host.
- [Token-Level SLOs](token-level-slos.md) — TTFT is determined by prefill time; ITL is determined by decode batch size; disaggregation makes both independently tunable.
- [KV Cache Pressure](kv-cache-pressure.md) — disaggregation requires KV transfer between hosts; transfer bandwidth is a new capacity constraint.
- [Inference Cold Starts](inference-cold-starts.md) — disaggregated systems require cold-starting both prefill and decode hosts; the multi-host startup sequence extends total cold-start time.

## References

- Zhong, Y. et al. "DistServe: Disaggregating Prefill and Decoding for Goodput-Optimized Large Language Model Serving." *OSDI 2024*.
  Primary reference for prefill-decode disaggregation; provides the hardware requirement analysis and 2–3.8× goodput measurement.
- Patel, P. et al. "Splitwise: Efficient Generative LLM Inference Using Phase Splitting." *ISCA 2024*.
  Architecture-level analysis of prefill and decode hardware utilization; confirms the compute/memory-bandwidth mismatch.
- Agrawal, A. et al. "Sarathi-Serve: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills." *OSDI 2024*.
  Chunked prefill as the alternative to disaggregation for handling the prefill-decode interference on shared hardware.
