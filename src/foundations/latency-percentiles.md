# Latency Percentiles

> The p99 of a fanout to 100 shards equals approximately the per-shard p99.99. Understanding why this is true — and why averaging p99 values across hosts is wrong — is prerequisite knowledge for diagnosing tail latency.

## What a percentile measures

The Nth percentile of a latency distribution answers: "what latency is faster than N% of requests?" The 99th percentile (p99) is the latency that 99% of requests fall below; equivalently, 1% of requests are slower.

The key properties:
- **p50 and p99 can move in opposite directions.** p50 is dominated by the bulk of the distribution; p99 is dominated by the tail. A GC pause that affects 0.5% of requests will raise p99 and p999 while leaving p50 flat.
- **p99 can be 10–100× p50.** In a lognormal distribution with occasional spikes (GC, page faults, connection setup), the p50 might be 5ms and the p99 300ms. These are not the same thing.
- **The p99 you see depends on sample size.** At 100 requests/second, you observe about 1 "p99 sample" per second. A 1-minute window gives you 60 samples of the tail. Rare events (one per 10,000 requests) may never appear in a 1-minute window at low traffic but are near-certain to appear during a 24-hour period.

## Why p99 diverges from p50

The observables that tell you *which* thing is slow:

| Pattern | p50 | p99 | CPU | Likely cause |
|---------|-----|-----|-----|--------------|
| p99 high, p50 flat, CPU low | stable | high | low | Stochastic tail: GC, page fault, one slow host |
| p99 and p50 rising together | rising | rising | high | Overload, queue building |
| p99 high, correlated with specific hosts | stable | high | varies | Hot shard, uneven LB distribution |
| p99 after scale-out | stable | high | low | Cold start: caches and JIT not warm |

## Fanout amplification

When a request fans out to N independent subqueries and returns when all N respond, the request latency is `max(L₁, L₂, ..., Lₙ)`. This maximum has a well-known statistical property:

> **P(max > t) = 1 − (1 − p)ᴺ**

where p is the per-shard probability of exceeding t.

For p = 0.01 (per-shard p99) and N = 100:

> P(max > t) = 1 − (0.99)¹⁰⁰ ≈ 0.634

63% of requests to 100 shards experience at least one shard above the per-shard p99. The effective fanout p99 is the per-shard value at a much higher percentile. Specifically, the Nth percentile of the max-of-N is approximately the `(1 - (1-N·p)/N)`th percentile of the individual distribution.

In practice: the p99 of a 100-shard fanout corresponds to approximately the per-shard p99.99. That's not an outlier — it's a regular occurrence at scale.

This is the core reason that adding more shards to improve throughput simultaneously degrades tail latency. The `fanout_p99` figure in [Fanout Amplification](../patterns/tail-latency/fanout-amplification.md) shows this curve.

## Percentile aggregation is not additive

The p99 of a fleet of hosts is not the average of their individual p99 values. If host A has p99 = 10ms and host B has p99 = 100ms (because it's slower), the fleet p99 is not 55ms — it's somewhere between 10ms and 100ms depending on the traffic split. If the slow host is receiving 10% of traffic, the fleet p99 might be close to the p99 of a 90/10 mixture.

To correctly compute fleet percentiles: use histogram-based metrics (Prometheus histograms, HDR Histogram) and merge the histograms before computing percentiles. Averaging pre-computed percentile values produces meaningless numbers.

## Reading tail latency in dashboards

When diagnosing a p99 issue, work through this sequence:

1. **Is p50 also affected?** If yes, the slow path is common, not rare. Suspect load, queue depth, or a downstream everyone is using.

2. **Is the spike correlated with a specific host?** Check per-host p99. One slow host can lift the fleet p99 even if all others are healthy. This is a different problem from a fleet-wide slow path.

3. **Is the spike periodic?** GC pauses in JVM/Go are periodic (related to allocation rate and heap pressure). A periodic p99 spike at irregular-but-frequent intervals is characteristic.

4. **Does it correlate with a downstream?** Check downstream latency at the same time. If the downstream p99 moved before yours, the cause is upstream.

5. **Is CPU low during the spike?** Low CPU + high p99 = the server is waiting on something: IO, locks, external calls. High CPU + high p99 = compute saturation or GC.

## Why small percentile changes at high percentiles are expensive

At 99% hit rate (1% miss), a 0.5% increase in miss rate to 1.5% multiplies backend load by 50% (from 1/100 to 1/98.5 of total traffic). At high hit rates, small changes in miss rate produce large changes in backend load. The same nonlinearity applies to percentile changes: moving from p99.9 to p99.99 is not a 10× increase in "rareness" — it's a 10× increase in the cost of capturing those events in a system with N-shard fanout.

## References

- Dean, J. and Barroso, L.A. "The Tail at Scale." *Communications of the ACM* 56(2), 2013.
  Section 1 shows the fanout math concisely; Section 3 covers hedged requests as the mitigation.
- Heinrich, H. *HdrHistogram*. https://hdrhistogram.github.io/HdrHistogram/
  The tool for recording high-dynamic-range latency distributions efficiently. Solves the aggregation problem correctly.
- Schwartz, B. and Tkachenko, V. *High Performance MySQL*. O'Reilly, 2012.
  Chapter 3 has a sharp discussion of why average latency is useless and p99 is the minimum useful metric.
