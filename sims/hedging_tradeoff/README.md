# hedging_tradeoff sim

## What it models

Simulates hedged requests against a server with lognormal + GC-spike latency.
Produces two figures:

1. P99 improvement vs hedge threshold percentile, at fixed utilization.
2. P99 improvement and hedge overhead vs utilization, at fixed threshold.

Shows the crossover: at low utilization, hedging improves P99 with modest overhead.
At high utilization, hedge rate rises (slow responses are common) and overhead
negates the improvement.

## Simplifying assumptions

- Hedge latency is an independent sample from the same distribution. In practice,
  a second request to the same backend pool may hit the same slow state.
- Hedges are always cancelled when the original responds (best-case scenario for
  overhead). In practice, cancellation may not be honored.
- Utilization is treated as a simple latency multiplier; real queueing dynamics
  are more complex.

## How to regenerate

```
cd ht-patterns
python sims/hedging_tradeoff/sim.py --out src/figures/hedging_tradeoff
```
