# continuous_batching sim

## What it models

Compares static batching (fixed batch, process together to completion) vs continuous
batching (iteration-level scheduling, complete sequences leave and new ones join).

Produces two figures:
1. TTFT distribution under both strategies — continuous batching reduces TTFT for
   late-arriving requests.
2. KV memory occupancy over time — shows how static batching holds KV slots until
   the longest sequence completes, while continuous batching releases them sooner.

## Simplifying assumptions

- Prefill time is linear in prompt length. Real transformer prefill has better
  GPU utilization at longer lengths due to tensor parallelism.
- Decode step time is constant per sequence regardless of sequence length (no KV
  scan cost). In practice, attention cost is O(sequence_length).
- No disaggregation (prefill and decode on same "GPU"). For disaggregation effects,
  see the referenced papers.
- KV memory fragmentation is not modeled (assumes PagedAttention or equivalent).

## How to regenerate

```
cd ht-patterns
python sims/continuous_batching/sim.py --out src/figures/continuous_batching
```
