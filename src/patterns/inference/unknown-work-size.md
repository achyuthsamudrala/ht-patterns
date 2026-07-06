# Unknown Work Size

> **One-liner:** Admission control for inference must commit to serving a request without knowing how long it will take — output length is determined during generation, not at admission, making KV memory reservation a bet rather than a booking.

## Symptom

- KV cache memory exhausted mid-generation, forcing the scheduler to preempt (evict) a running sequence.
- A batch predicted to fit in memory OOMs because several requests generated far more tokens than expected.
- Admission control based on prompt length allows too many long-output requests simultaneously.
- Throughput lower than hardware capacity suggests because batch slots are occupied by very long sequences.

## Mechanism

**The classical admission problem:**

In conventional serving, request cost at admission time is approximately known. A database query's cost is bounded by its query plan; an image resize operation's cost is proportional to input dimensions. The scheduler can compute "do I have capacity to serve this request?" and make a binary admit/reject decision with high confidence.

**Token generation changes the contract:**

In autoregressive token generation, output length is determined by the model's sampling process — a sequence of probabilistic choices, one per output token, that continues until the model generates an end-of-sequence token or the caller's `max_tokens` limit is reached.

- "Write me a haiku" → ~20 tokens.
- "Explain quantum computing in detail" → 1,500 tokens.
- "Tell me a story" → anywhere from 50 to 2,000 tokens depending on the model's sampling.

Both requests have the same *input* length and are indistinguishable at admission time based on prompt characteristics alone.

**KV cache as the scarce resource:**

The KV cache for a sequence grows with every output token generated. At admission, only the prompt's KV footprint is known. A sequence admitted with a 256-token prompt may consume 50 MB of KV cache after generating 2,000 tokens — roughly 100× its admission-time footprint.

KV memory formula per sequence:
```
KV_bytes(n_tokens) = 2 × num_layers × num_heads × head_dim × n_tokens × dtype_bytes
```

For a typical 7B model (fp16, 32 layers, 32 heads, 128 head_dim):
```
KV_bytes = 2 × 32 × 32 × 128 × n_tokens × 2 = 524 KB per 1000 tokens
```

A 40 GB HBM GPU with 20 GB reserved for weights has ~20 GB for KV. With 100 active sequences averaging 1,000 output tokens: 52 GB required — 2.6× the available budget.

**Admission strategies under uncertainty:**

| Strategy | Mechanism | Risk |
|---------|-----------|------|
| Prompt-length-only | Reserve KV for prompt tokens | Under-reservation; OOM when output grows |
| max_tokens cap | Reserve KV for full `max_tokens` | Over-reservation; low concurrency |
| Mean output predictor | Reserve E[output_len] + buffer | Outliers exceed reservation |
| Pessimistic (worst case) | Reserve `max_tokens` always | Lowest concurrency, highest stability |

## Real-world sightings

**Sarathi-Serve (Agrawal et al., OSDI 2024).** The paper explicitly identifies output length unpredictability as the fundamental challenge for inference scheduling. The paper proposes chunked prefill partially as a response: by processing sequences in chunks, the scheduler can make more frequent admission decisions and adapt to actual (vs. predicted) output lengths in progress.

**vLLM (Kwon et al., SOSP 2023).** The vLLM system addresses unknown work size via preemption: admit sequences without reserving full KV budget; if memory is exhausted, evict the lowest-priority sequence and requeue it. This moves the risk from admission-time estimation errors to runtime preemption cost.

## Mitigations

### max_tokens pessimistic reservation

**What it is:** At admission, reserve KV memory for the caller's `max_tokens` value (the upper bound on output length). Admit only if this worst-case reservation fits within the budget.

**Cost:** Low concurrency — most sequences use far fewer tokens than `max_tokens`. A 4096 `max_tokens` limit with typical 200-token outputs wastes 95% of reserved KV slots.

**How it backfires:** Callers who set high `max_tokens` "just in case" block far more concurrency than their actual usage warrants. Consider capping the max_tokens value the scheduler will reserve for (e.g., reserve for min(max_tokens, 512) and preempt if exceeded).

### Output length prediction

**What it is:** Train a small classifier or regressor on input features (prompt length, prompt content, caller, endpoint) to predict output length distribution. Use the prediction's mean or 95th percentile as the reservation.

**Cost:** Requires training data (historical output lengths per request class) and inference overhead for the predictor. Prediction errors cause over- or under-reservation.

**How it backfires:** The long tail of actual lengths exceeds even the 95th-percentile prediction for a fraction of requests. Must still handle over-budget sequences via preemption.

### Preemption as the safety valve

**What it is:** Use optimistic admission (reserve only prompt-length KV) and implement preemption: when memory is exhausted, evict the lowest-priority or least-progressed sequence. The evicted sequence is requeued; on readmission, its prompt is re-prefilled and generation resumes.

**Cost:** Re-prefill wastes compute (proportional to prompt length). High preemption rate indicates the admission policy is too optimistic.

**How it backfires:** Repeated preemption of the same sequence (if memory pressure is sustained) can starve it indefinitely. Add a maximum preemption count or priority escalation for repeatedly evicted sequences.

## Interactions

- [KV Cache Pressure](kv-cache-pressure.md) — unknown work size makes KV memory occupancy inherently unpredictable; KV pressure is the consequence.
- [Priority and Preemption](priority-and-preemption.md) — preemption is the safety valve for admission estimation errors.
- [Cost-Aware Quotas](../multitenancy/cost-aware-quotas.md) — per-tenant KV quotas must be set without knowing each request's actual output length.
- [Batching](../pipeline/batching.md) — batch assembly is complicated when items have unknown processing cost.

## References

- Kwon, W. et al. "Efficient Memory Management for Large Language Model Serving with PagedAttention." *SOSP 2023*.
  Introduces preemption as the response to unknown output length; describes the trade-off between reservation and preemption cost.
- Agrawal, A. et al. "Sarathi-Serve: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills." *OSDI 2024*.
  Discusses chunked prefill as a mechanism for more responsive scheduling under uncertain output lengths.
