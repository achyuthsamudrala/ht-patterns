#!/usr/bin/env python3
"""
Cache-down backend load multiplier.

Shows how backend load scales with cache hit rate, and where the provisioned
capacity line sits.

Usage:
    python sim.py --out ../../src/figures/cache_down_multiplier

Output:
    cache_down_multiplier.svg — backend load (× normal) vs cache hit rate
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def backend_load_multiplier(hit_rate: float) -> float:
    """
    Backend load relative to steady-state operating load.

    At operating hit rate H_op, backends see fraction (1 - H_op) of total traffic.
    Define this as 1.0 (normalized baseline).

    At any hit rate H, backend load = (1 - H) / (1 - H_op).
    At H = 0 (cache fully down): load = 1 / (1 - H_op).
    """
    return 1.0 / (1.0 - hit_rate) if hit_rate < 1.0 else float("inf")


def main():
    parser = argparse.ArgumentParser(description="Cache down multiplier")
    parser.add_argument("--out", type=Path, default=Path("../../src/figures/cache_down_multiplier"))
    parser.add_argument("--normal-hit-rate", type=float, default=0.90,
                        help="Normal operating hit rate (default: 0.90)")
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    H_op = args.normal_hit_rate

    # Backend load is relative to the load at the operating hit rate.
    # Normalize so that H = H_op → load = 1.0.
    hit_rates = np.linspace(0.0, 0.99, 400)
    absolute_multiplier = np.array([1.0 / (1.0 - h) for h in hit_rates])
    normalized = absolute_multiplier / (1.0 / (1.0 - H_op))

    # Provisioned capacity = 1.0 (by construction at H_op)
    provisioned = 1.0

    fig, ax = plt.subplots()

    ax.plot(hit_rates * 100, normalized, color="#0072B2", linewidth=2.0,
            label="Backend load (normalized)")

    # Provisioned capacity line
    ax.axhline(provisioned, color="#E69F00", linestyle="--", linewidth=1.5,
               label=f"Provisioned capacity (H = {H_op:.0%})")

    # Operating point annotation
    ax.axvline(H_op * 100, color="gray", linestyle=":", linewidth=1.0, alpha=0.6)
    ax.annotate(f"Operating point\nH = {H_op:.0%}\n(1× load)",
                xy=(H_op * 100, 1.0), xytext=(H_op * 100 - 18, 4.5),
                fontsize=9, color="gray",
                arrowprops=dict(arrowstyle="->", color="gray", lw=0.8))

    # Cache-down annotation
    load_at_zero = 1.0 / (1.0 - H_op)
    ax.annotate(f"Cache fully down\n({load_at_zero:.0f}× provisioned load)",
                xy=(0, normalized[0]), xytext=(8, normalized[0] * 0.85),
                fontsize=9,
                arrowprops=dict(arrowstyle="->", color="#0072B2", lw=0.8))

    ax.set_xlabel("Cache Hit Rate (%)")
    ax.set_ylabel(f"Backend Load (× operating load at H = {H_op:.0%})")
    ax.set_title("Cache Failure: Backend Load Multiplier vs. Hit Rate")
    ax.set_xlim(-1, 99)
    ax.set_ylim(0, load_at_zero * 1.15)
    ax.legend(loc="upper right")

    out_path = args.out / "cache_down_multiplier.svg"
    fig.savefig(out_path, format="svg")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
