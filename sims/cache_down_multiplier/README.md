# cache_down_multiplier sim

## What it models

Plots backend load (normalized to normal operating load) as a function of cache
hit rate, from 0% to 99%. Annotates the provisioned capacity line based on the
normal operating hit rate.

The key insight: at 90% hit rate, a cache failure multiplies backend load by 10×.
At 99% hit rate, by 100×. This is a purely analytical result, not a simulation.

## Simplifying assumptions

- Backend provisioned exactly for the cache-miss fraction at the normal hit rate.
- Requests are uniform cost.
- No admission control at the backend (all misses become backend requests).
- No partial degradation: either full hit rate or zero hit rate.

## How to regenerate

```
cd ht-patterns
python sims/cache_down_multiplier/sim.py --out src/figures/cache_down_multiplier
```
