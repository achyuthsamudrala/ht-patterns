# goodput_collapse sim

## What it models

An M/M/c queue (c servers, Poisson arrivals, exponential service times) with a
per-request timeout. As offered load exceeds capacity (λ > μc), queuing time
grows, requests exceed their timeout before being served, and goodput falls.

The figure shows the characteristic cliff shape: goodput ≈ offered load below
saturation, then collapse above it.

## Simplifying assumptions

- Poisson arrivals (memoryless inter-arrival times).
- Exponential service times (memoryless, which is unrealistic — real service time
  distributions have heavier tails).
- Timeout is measured from arrival, not from queue entry. In practice, the timeout
  includes transmission time.
- No retries. Adding retries would show the metastable failure mechanism.

## Parameters

| Parameter | Default | Meaning |
|-----------|---------|---------|
| `--servers` | 10 | Number of parallel workers (c) |
| `--service-rate` | 1.0 | Requests/second per server (μ) |
| `--timeout` | 3.0 | Per-request timeout (seconds) |

## How to regenerate

```
cd ht-patterns
python sims/goodput_collapse/sim.py --out src/figures/goodput_collapse
```

Or via Make:

```
make figures
```
