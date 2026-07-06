# Priority and Preemption

> **One-liner:** When KV memory is exhausted, the scheduler must evict a running sequence — without explicit priority, it may evict a nearly-complete high-priority request to make room for a new low-priority one, wasting both the evicted work and the re-prefill compute.

## Symptom

- High-priority requests being preempted while low-priority requests hold KV slots.
- Preemption rate increasing with KV memory pressure (visible in scheduler metrics).
- High-priority requests experiencing TTFT spikes that correlate with preemption events.
- Throughput lower than expected because compute is being spent on re-prefill of evicted sequences.
- Sequences at 90% completion evicted to make room for new admissions.

## Mechanism

**Why preemption happens:**

When all KV pages are allocated and a new sequence needs to be admitted (or an in-progress sequence generates more tokens than its reserved budget), the scheduler must free pages. It selects one or more sequences to preempt: their KV pages are freed (possibly after swapping to CPU RAM), and they are returned to the admission queue. On re-admission, their prompt must be re-prefilled before decode can resume.

**The priority-free preemption failure:**

Without priority metadata on sequences, the scheduler's only basis for eviction is:
- FIFO (oldest sequences evicted first) — evicts sequences closest to completion.
- LIFO (newest sequences evicted first) — evicts sequences with least progress.
- Random — no predictable behavior.

FIFO is worst: it preferentially evicts sequences near completion, wasting the most compute. LIFO (smallest number of generated tokens) minimizes wasted re-prefill work but ignores the business priority of the evicted requests.

**Priority dimensions for inference scheduling:**

| Priority source | Mechanism |
|----------------|-----------|
| Tenant tier | Premium tenants' sequences are never evicted before free-tier sequences |
| Request urgency | Interactive requests (streaming, user-facing) rank above batch jobs |
| Completion fraction | Sequences at 90% completion rank above sequences at 10% (minimize waste) |
| Queue wait time | Sequences waiting longest get priority escalation (starvation prevention) |

Effective scheduling uses a composite score combining multiple dimensions.

**The preemption cost model:**

Cost of preempting sequence with prompt_len = P and generated_tokens = G:
- Discard-and-recompute: re-prefill costs O(P) compute on next admission.
- Swap to CPU: transfer P × G KV pages over PCIe (~31ms per GB at PCIe 4.0).
- Not preempting: O(1/remaining_sequences) throughput reduction.

The preemption decision is cost-beneficial when `compute_cost_of_requeue < opportunity_cost_of_keeping_low_priority_sequence`. For near-complete sequences, re-prefill cost is near-constant (prompt only); for early-stage sequences, re-prefill is cheap (prompt is short or not yet generated). This argues for preempting early-stage sequences.

**Starvation under sustained pressure:**

A low-priority sequence under sustained KV pressure may be evicted every time it makes progress. After several eviction cycles, it has never completed despite spending O(P × eviction_count) compute on repeated prefill. A starvation counter must escalate priority after a configurable number of evictions.

## Real-world sightings

**vLLM preemption implementation.** vLLM implements preemption as part of its continuous batching scheduler. When KV pages are exhausted, vLLM selects the last-admitted sequence for eviction (LIFO within a batch) to minimize re-prefill cost. The evicted sequence is requeued and re-prefilled on next admission. Priority-based preemption was added in later versions to support multi-tenant serving.

**Sarathi-Serve (Agrawal et al., OSDI 2024).** The paper proposes chunked prefill as a way to reduce re-prefill cost after preemption: if the evicted sequence's prompt is chunked, only the remaining un-computed chunks need to be re-run on re-admission, not the entire prompt. This directly reduces the waste associated with preemption.

## Mitigations

### Priority-ordered preemption (evict lowest priority first)

**What it is:** Tag each sequence at admission with a priority derived from the request's tenant tier, request type (interactive vs. batch), and any explicit priority field in the request. When preemption is needed, select the sequence with the lowest composite priority. Among sequences at the same priority level, prefer those with the smallest token count (least compute wasted).

**Cost:** Requires priority metadata on all requests; low-priority sequences under sustained pressure may be perpetually preempted (starvation).

**How it backfires:** If priority metadata is not set (default priority for all requests), priority-ordered preemption degenerates to an arbitrary ordering. Every request type must be assigned a meaningful priority for this to work.

### Progress-preserving preemption selection

**What it is:** When choosing which sequence to preempt, prefer sequences with fewer generated tokens over those with more. The cost of re-running a sequence with G generated tokens and P prompt tokens is proportional to P (re-prefill of the prompt); choosing sequences with small G means the eviction discards less compute progress while minimizing re-prefill overhead.

**Cost:** May conflict with priority ordering: a high-progress, high-priority sequence avoids eviction; a low-progress, low-priority sequence is evicted repeatedly.

**How it backfires:** Perpetually prioritizing low-progress sequences for eviction can cause them to never make progress (they are evicted before reaching significant token count). Set a minimum token count threshold below which a sequence is eligible for eviction but above which it is protected.

### Priority escalation (starvation prevention)

**What it is:** Track the number of times a sequence has been preempted. After K evictions, escalate its priority to prevent further eviction. This guarantees that no sequence is evicted indefinitely, bounding worst-case TTFT to K × re_prefill_time + decode_time.

**Cost:** Long-waiting low-priority sequences will eventually acquire high priority and compete with genuinely high-priority sequences.

**How it backfires:** If K is too small, a long-running memory pressure event elevates all sequences to high priority, making priority-based scheduling useless. K must be large enough that starvation is truly rare, but small enough to provide a meaningful upper bound.

## Interactions

- [KV Cache Pressure](kv-cache-pressure.md) — preemption is the response to KV memory exhaustion; priority determines which sequences are evicted.
- [Unknown Work Size](unknown-work-size.md) — output length uncertainty makes KV footprint unpredictable, increasing the frequency of memory-driven preemption events.
- [Token-Level SLOs](token-level-slos.md) — preemption directly violates TTFT SLOs for re-admitted sequences (re-prefill adds to their effective TTFT).
- [Fair Scheduling](../multitenancy/fair-scheduling.md) — multi-tenant priority and per-tenant fair scheduling interact: a high-priority tenant may have low-priority requests that should still be served eventually.

## References

- Kwon, W. et al. "Efficient Memory Management for Large Language Model Serving with PagedAttention." *SOSP 2023*.
  Describes vLLM's preemption mechanism and the choice between swap-to-CPU and recompute.
- Agrawal, A. et al. "Sarathi-Serve: Efficient LLM Inference by Piggybacking Decodes with Chunked Prefills." *OSDI 2024*.
  Chunked prefill reduces re-prefill cost after preemption; the interaction with preemption strategy is discussed in Sections 4–5.
