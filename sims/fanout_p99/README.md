# fanout_p99 sim

## What it models

Simulates per-shard latency using a lognormal distribution with 1% GC spikes.
For each fanout width N, the request latency is the maximum across N shards.
Plots request P99 vs fanout width.

## Simplifying assumptions

- Per-shard latencies are independent. In practice, shards on the same host or
  experiencing the same GC cycle are correlated — this underestimates worst-case.
- GC spikes are 50× the median latency, 1% of requests. Real distributions vary.
- No hedging or retry. See the hedging_tradeoff sim for the mitigation.

## How to regenerate

```
cd ht-patterns
python sims/fanout_p99/sim.py --out src/figures/fanout_p99
```
