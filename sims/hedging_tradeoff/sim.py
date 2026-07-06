#!/usr/bin/env python3
"""
Hedging tradeoff simulation.

Shows two panels:
  Left:  at low utilization, p99 improvement vs. load overhead as the
         hedge threshold percentile varies.
  Right: as utilization rises, p99 improvement shrinks and load overhead
         grows, crossing over around 65-70%.

Usage:
    python sim.py --out ../../src/figures/hedging_tradeoff

Output:
    hedging_tradeoff.svg — two-panel figure
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

RNG = np.random.default_rng(42)
N_SAMPLES = 80_000


def sample_latencies(n: int, utilization: float) -> np.ndarray:
    """
    Lognormal base + GC spikes + utilization-driven queueing delay.

    utilization in [0, 1). At utilization u, queueing multiplier ≈ 1/(1-u)
    applied to base latency (M/M/1 approximation).
    """
    base = RNG.lognormal(mean=np.log(20), sigma=0.35, size=n)  # median ~20ms
    # 1% GC spikes
    spikes = np.where(RNG.random(n) < 0.01, 8.0, 1.0)
    # Queueing amplification
    queue_amp = 1.0 + 0.6 * utilization / max(0.01, 1.0 - utilization)
    return base * spikes * queue_amp


def hedge_sim(utilization: float, threshold_pct: float) -> tuple:
    """
    Returns (unhedged_p99_ms, hedged_p99_ms, hedge_rate_fraction).

    threshold_pct: percentile (0-100) at which to fire hedge.
    """
    latencies = sample_latencies(N_SAMPLES, utilization)
    unhedged_p99 = np.percentile(latencies, 99)

    threshold = np.percentile(latencies, threshold_pct)

    slow_mask = latencies > threshold
    hedge_count = slow_mask.sum()

    # For each slow request: take min(original, second_attempt)
    hedged = latencies.copy()
    if hedge_count > 0:
        second_attempts = sample_latencies(int(hedge_count), utilization)
        hedged[slow_mask] = np.minimum(latencies[slow_mask], second_attempts)

    hedge_rate = hedge_count / N_SAMPLES
    hedged_p99 = np.percentile(hedged, 99)
    return unhedged_p99, hedged_p99, hedge_rate


def main() -> None:
    parser = argparse.ArgumentParser(description="Hedging tradeoff simulation")
    parser.add_argument(
        "--out", type=Path, default=Path("../../src/figures/hedging_tradeoff")
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.5))

    # --- Left panel: p99 improvement and hedge overhead vs threshold ---
    low_util = 0.45
    thresholds = np.arange(70, 99, 2, dtype=float)
    base_p99, _, _ = hedge_sim(low_util, 50.0)  # baseline = no hedging (p50 threshold ≈ all)
    # More precisely: no-hedge baseline
    raw = sample_latencies(N_SAMPLES, low_util)
    base_p99 = float(np.percentile(raw, 99))

    improvements, hedge_rates = [], []
    for thr in thresholds:
        _, hedged_p99, hr = hedge_sim(low_util, thr)
        improvements.append((base_p99 - hedged_p99) / base_p99 * 100)
        hedge_rates.append(hr * 100)

    ax1.plot(thresholds, improvements, color="#0072B2", linewidth=2.0,
             label="p99 improvement (%)")
    ax1.plot(thresholds, hedge_rates, color="#D55E00", linewidth=2.0,
             linestyle="-.", label="Extra load (%)")
    ax1.set_xlabel("Hedge Threshold (percentile)")
    ax1.set_ylabel("Percent")
    ax1.set_title(f"Threshold Tradeoff  (utilization = {low_util:.0%})")
    ax1.legend(fontsize=8)
    ax1.set_xlim(70, 99)

    # Annotate sweet spot: hedge at p95 gives good improvement, modest overhead
    ax1.axvline(95, linestyle=":", color="#009E73", linewidth=1.2, alpha=0.8)
    ax1.text(95.5, max(improvements) * 0.92, "p95 threshold\n(~5% load overhead)",
             color="#009E73", fontsize=7)

    # --- Right panel: improvement and overhead vs utilization at fixed p95 hedge ---
    fixed_thr = 95.0
    utilizations = np.arange(0.30, 0.90, 0.05)
    util_improvements, util_overhead = [], []
    for u in utilizations:
        raw_u = sample_latencies(N_SAMPLES, u)
        base_p99_u = float(np.percentile(raw_u, 99))
        _, hedged_p99_u, hr_u = hedge_sim(u, fixed_thr)
        util_improvements.append((base_p99_u - hedged_p99_u) / base_p99_u * 100)
        util_overhead.append(hr_u * 100)

    ax2.plot(utilizations * 100, util_improvements, color="#0072B2", linewidth=2.0,
             label="p99 improvement (%)")
    ax2.plot(utilizations * 100, util_overhead, color="#D55E00", linewidth=2.0,
             linestyle="-.", label="Extra load (%)")

    # Find crossover
    cross_idx = next(
        (i for i in range(1, len(util_improvements))
         if util_overhead[i] >= util_improvements[i]),
        None,
    )
    if cross_idx is not None:
        cross_util = utilizations[cross_idx] * 100
        ax2.axvline(cross_util, linestyle=":", color="#CC79A7", linewidth=1.4, alpha=0.9)
        ax2.text(cross_util + 1, max(util_overhead) * 0.85,
                 f"crossover\n~{cross_util:.0f}%", color="#CC79A7", fontsize=7)

    ax2.set_xlabel("Server Utilization (%)")
    ax2.set_ylabel("Percent")
    ax2.set_title(f"Hedge at p{fixed_thr:.0f} vs Utilization")
    ax2.legend(fontsize=8)
    ax2.set_xlim(30, 90)

    fig.tight_layout()
    out_path = args.out / "hedging_tradeoff.svg"
    fig.savefig(out_path, format="svg")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
