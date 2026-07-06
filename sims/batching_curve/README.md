# batching_curve sim

## What it models

Plots the latency-throughput frontier for different batch sizes and arrival rates.
Each batch incurs a fixed overhead plus per-item cost. Larger batches amortize
overhead but increase wait time for the first item in the batch.

## Simplifying assumptions

- Items arrive uniformly within a fill window. Real arrivals are bursty (Poisson),
  which increases fill time variance and raises P99.
- Batch processing time is deterministic (overhead + batch_size × per_item_cost).
  In practice, GPU inference batch time has variance.
- No queue buildup: assumes arrival rate ≤ processing rate. Near-saturation
  behavior is not modeled.

## How to regenerate

```
cd ht-patterns
python sims/batching_curve/sim.py --out src/figures/batching_curve
```
