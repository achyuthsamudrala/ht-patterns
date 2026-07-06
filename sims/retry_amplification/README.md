# retry_amplification sim

## What it models

Clients retrying failed requests against a server with a given error rate.
Shows effective load multiplier (actual requests / original requests) as a
function of server error rate, with and without a retry budget.

## Simplifying assumptions

- Each retry is independent (no exponential backoff or jitter modeled).
- Retry budget is a fraction of arrival rate applied globally (not per-client).
- Error rate is constant across all request attempts. In practice, a server
  under amplified load will have a higher error rate, creating positive feedback
  (the metastable loop).

## How to regenerate

```
cd ht-patterns
python sims/retry_amplification/sim.py --out src/figures/retry_amplification
```
