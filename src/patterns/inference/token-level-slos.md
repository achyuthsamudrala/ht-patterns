# Token-Level SLOs

> **One-liner:** Inference has three distinct latency dimensions — time-to-first-token, inter-token latency, and throughput — and they trade against each other; a combined "latency" SLO masks which one is violated and why.

## Symptom

- TTFT SLO met; users complain of stuttering output — ITL is violated.
- ITL SLO met; users complain of slow initial response — TTFT is violated.
- Throughput target met (tokens/sec across all users); individual user experience poor because both TTFT and ITL are degraded.
- "Latency p99" in a dashboard is ambiguous — it may be measuring only TTFT, only ITL, or end-to-end completion latency; alerts fire but the cause is unclear.

## Mechanism

**Three distinct user-facing dimensions:**

**TTFT (Time to First Token):** Time from request submission to when the first output token is delivered. Measures responsiveness — "how long before anything happens." TTFT is dominated by:
- Queue wait time (how long before the scheduler processes this request).
- Prefill time (processing the input prompt, proportional to prompt length).

For interactive use (chat, copilot), TTFT > 2 seconds is perceivable as a lag; TTFT > 5 seconds is user-frustrating. For background batch jobs, TTFT may not matter.

**ITL (Inter-Token Latency, also TBT — Time Between Tokens):** Time between consecutive output tokens during streaming. Measures streaming smoothness — "how fast does text appear." ITL is dominated by:
- Decode batch size (larger batch → more KV reads per decode step → slower per-step).
- KV memory bandwidth (the binding constraint during decode).
- Decode compute load (model size, quantization).

For human-readable text generation, ITL > 50ms is perceivable as a stutter; ITL > 100ms makes the output visually choppy.

**Output token throughput (TPS):** Total tokens generated per second across all users. System-level metric; reflects cost efficiency. Not directly user-perceivable, but determines how many users can be served simultaneously at given TTFT and ITL.

**The three-way tradeoff:**

| Optimization | TTFT effect | ITL effect | TPS effect |
|-------------|------------|-----------|-----------|
| Maximize decode batch size | Worse (queue wait) | Worse (more KV reads) | Better |
| Prioritize prefill | Better | Worse (decode deferred) | Neutral |
| Minimize batch size | Better | Better | Worse |
| Disaggregate prefill/decode | Better (prefill isolated) | Better (decode isolated) | Depends on fleet sizing |

No single configuration simultaneously minimizes TTFT, minimizes ITL, and maximizes TPS. The operating point is a policy choice based on workload priority.

**Why combined latency metrics hide the problem:**

An end-to-end "latency" metric (time from request submission to final token) combines TTFT + sum(ITL) over all output tokens. For a 1000-token response with 100ms ITL and 500ms TTFT: total latency = 500ms + 1000 × 100ms = 100.5 seconds. The TTFT component (0.5%) is invisible in this metric. An alert on total latency fires when ITL is violated but not when TTFT degrades. Conversely, a TTFT-only alert fires when prefill is slow but doesn't capture a smooth-but-slow token stream.

**Goodput redefined for inference:**

A token-generation request must satisfy all three SLO dimensions to count as "good":
- TTFT ≤ T_ttft_slo
- max(ITL) ≤ T_itl_slo
- Response completes before client deadline

A request that generates all tokens but violates TTFT or ITL SLO is not goodput.

## Real-world sightings

**Zhong et al. "DistServe" (OSDI 2024).** Section 2 of the paper provides the formal definition of TTFT and TBT SLOs and demonstrates that they require fundamentally different hardware configurations. The paper shows empirically that sharing hardware between prefill and decode forces suboptimal compromises on both, motivating disaggregation.

**OpenAI API documentation.** OpenAI's streaming API delivers tokens as they are generated, making ITL directly visible to users. OpenAI's status page reports incidents separately for "increased latency" (TTFT) and "slow streaming" (ITL), confirming that operators track these as separate failure modes.

## Mitigations

### Separate TTFT and ITL SLO tracking and alerting

**What it is:** Instrument and alert on TTFT and ITL independently. For streaming requests: record the timestamp of the first token for TTFT; record inter-token intervals for ITL (p99 of intervals). Alert when either dimension exceeds its SLO, with separate alert labels.

**Cost:** More instrumentation work; more alerting rules. Client-side instrumentation may be needed for ITL (server knows when it sends tokens; whether the client receives them promptly depends on network).

**How it backfires:** ITL is measured server-side (time between scheduling decode steps); client-side ITL may differ due to network jitter and buffering. For latency-critical workloads, measure both.

### Throughput-latency operating point selection

**What it is:** Explicitly choose a decode batch size based on the ITL SLO. A smaller batch size gives lower ITL at the cost of lower throughput; a larger batch improves throughput at the cost of higher ITL. The operating point is: find the maximum batch size such that decode-step time ≤ ITL_slo.

For a decode step time model: `decode_step_ms ≈ model_layers × kv_bandwidth_bound(batch_size)`. Given ITL SLO of 50ms: find max batch size where decode_step_ms ≤ 50ms.

**Cost:** Must be re-calibrated per model and hardware; the relationship between batch size and decode latency varies with quantization, KV cache format, and hardware generation.

**How it backfires:** The ITL-optimal batch size may be too small to meet the throughput target. The conflict must be resolved by adding hardware capacity (more GPUs), not by relaxing one SLO or the other.

### Prefill-decode disaggregation for independent tuning

**What it is:** Route prefill to dedicated prefill hosts; route decode to dedicated decode hosts. Each fleet is independently sized and tuned:
- Prefill hosts: maximize compute throughput (large batch size, no decode interference).
- Decode hosts: minimize memory bandwidth pressure (smaller batch, prioritize KV bandwidth).

**Cost:** Requires KV cache transfer between prefill and decode hosts after prefill completes. Inter-host bandwidth (NVLink or InfiniBand) must be sufficient; transfer latency adds to TTFT.

**How it backfires:** For short-prompt, short-output requests, the disaggregation overhead (transfer + coordination) may exceed the benefit. Short prompts are better served on a co-located system; disaggregation is most beneficial for long-context or long-output workloads.

## Interactions

- [Prefill vs. Decode](prefill-vs-decode.md) — the two compute phases that produce TTFT and ITL respectively.
- [Continuous Batching](continuous-batching.md) — the batch size parameter that controls the throughput-ITL tradeoff.
- [Goodput vs. Throughput](../../foundations/goodput-vs-throughput.md) — the goodput definition extended for multi-dimensional SLOs.

## References

- Zhong, Y. et al. "DistServe: Disaggregating Prefill and Decoding for Goodput-Optimized Large Language Model Serving." *OSDI 2024*.
  Formal definition of TTFT/TBT SLO dimensions and empirical demonstration of their hardware requirements.
- Patel, P. et al. "Splitwise: Efficient Generative LLM Inference Using Phase Splitting." *ISCA 2024*.
  Complementary disaggregation analysis from the hardware architecture perspective.
