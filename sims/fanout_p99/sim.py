#!/usr/bin/env python3
"""
Fanout P99 amplification simulation.

Shows how per-request latency percentiles degrade with fanout width.
For N shards, the request latency is max(L_1, ..., L_N).

The key result: P(max > t) = 1 - (1-p)^N amplifies the per-shard tail
exponentially with fan width.

Usage:
    python sim.py --out ../../src/figures/fanout_p99

Output:
    fanout_p99.svg — effective request P99 vs fanout width at several
                     per-shard GC spike probabilities
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

RNG = np.random.default_rng(42)
N_SAMPLES = 200_000


def per_shard_latency(n: int, gc_prob: float) -> np.ndarray:
    """
    Lognormal base + GC spike overlay.

    gc_prob: probability of a GC pause (50ms spike on ~10ms base).
    """
    base = RNG.lognormal(mean=np.log(10), sigma=0.35, size=n)  # median ~10ms
    spikes = RNG.random(n) < gc_prob
    return np.where(spikes, base + 50.0, base)


def fanout_p_pct(fan_width: int, gc_prob: float, pct: float = 99) -> float:
    """pct-th percentile of max(L_1, ..., L_fan_width)."""
    shards = np.column_stack(
        [per_shard_latency(N_SAMPLES, gc_prob) for _ in range(fan_width)]
    )
    return np.percentile(shards.max(axis=1), pct)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fanout P99 amplification")
    parser.add_argument(
        "--out", type=Path, default=Path("../../src/figures/fanout_p99")
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    fan_widths = [1, 2, 5, 10, 25, 50, 100, 200, 500]
    gc_scenarios = [
        (0.001, "0.1% GC spike prob",  "#0072B2"),
        (0.01,  "1% GC spike prob",    "#D55E00"),
        (0.05,  "5% GC spike prob",    "#CC79A7"),
    ]

    fig, ax = plt.subplots(figsize=(7, 4.5))

    single_p50 = np.percentile(per_shard_latency(N_SAMPLES, 0.0), 50)

    for gc_prob, label, color in gc_scenarios:
        p99s = [fanout_p_pct(w, gc_prob) for w in fan_widths]
        ax.plot(fan_widths, p99s, marker="o", markersize=4,
                color=color, linewidth=2.0, label=label)

    ax.axhline(single_p50, linestyle="--", color="#999999", linewidth=1.0,
               label="Per-shard p50 (no fanout)")

    # Annotation at N=100, GC=1%
    p99_at_100 = fanout_p_pct(100, 0.01)
    ax.annotate(
        f"N=100, 1% spikes\np99 = {p99_at_100:.0f}ms",
        xy=(100, p99_at_100),
        xytext=(60, p99_at_100 * 0.7),
        fontsize=7.5,
        color="#D55E00",
        arrowprops=dict(arrowstyle="->", color="#D55E00", lw=0.8),
    )

    ax.set_xscale("log")
    ax.set_xlabel("Fanout Width N (log scale)")
    ax.set_ylabel("Composed Request p99 Latency (ms)")
    ax.set_title("P99 Amplification  P(max > t) = 1 − (1−p)ᴺ")
    ax.legend(loc="upper left", fontsize=8)

    fig.tight_layout()
    out_path = args.out / "fanout_p99.svg"
    fig.savefig(out_path, format="svg")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
