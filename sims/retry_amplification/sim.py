#!/usr/bin/env python3
"""
Retry amplification simulation.

Shows how effective server load grows as a function of server error rate,
with different retry strategies (no retries, unlimited, capped budget, full jitter).

Usage:
    python sim.py --out ../../src/figures/retry_amplification

Output:
    retry_amplification.svg
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt


def multiplier_unlimited(error_rate: float, max_retries: int = 10) -> float:
    """
    Load multiplier with geometric retry series, no budget cap.

    Each failed attempt generates one more attempt. With error rate e and
    max_retries R, expected attempts per original request:
        1 + e + e^2 + ... + e^R  = (1 - e^(R+1)) / (1 - e)
    """
    if error_rate >= 1.0:
        return float(max_retries + 1)
    total = 0.0
    p = 1.0
    for _ in range(max_retries + 1):
        total += p
        p *= error_rate
    return total


def multiplier_budget(error_rate: float, budget_fraction: float = 0.10) -> float:
    """
    Load multiplier with retry budget cap.

    The budget allows at most budget_fraction * base_rate retries per second.
    Effective multiplier = min(geometric_series, 1 + budget_fraction).
    """
    uncapped = multiplier_unlimited(error_rate, max_retries=10)
    return min(uncapped, 1.0 + budget_fraction)


def multiplier_jitter(error_rate: float, max_retries: int = 3,
                      jitter_spread: float = 2.0) -> float:
    """
    Load multiplier with full jitter backoff.

    Full jitter desynchronizes retries: at high error rates the retry
    attempts spread over time, reducing instantaneous amplification.
    Approximated as: effective_multiplier ≈ multiplier_unlimited / jitter_spread
    (jitter_spread > 1 captures the spreading effect).
    """
    if error_rate < 0.5:
        return multiplier_unlimited(error_rate, max_retries=max_retries)
    spread = 1.0 + (jitter_spread - 1.0) * ((error_rate - 0.5) / 0.5)
    return multiplier_unlimited(error_rate, max_retries=max_retries) / spread


def main() -> None:
    parser = argparse.ArgumentParser(description="Retry amplification simulation")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../../src/figures/retry_amplification"),
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    error_rates = np.linspace(0.0, 0.90, 200)

    m_unlimited = [multiplier_unlimited(e, max_retries=3) for e in error_rates]
    m_budget = [multiplier_budget(e, budget_fraction=0.10) for e in error_rates]
    m_jitter = [multiplier_jitter(e, max_retries=3, jitter_spread=3.0) for e in error_rates]

    fig, ax = plt.subplots(figsize=(7, 4.5))

    ax.plot(error_rates * 100, m_unlimited, color="#D55E00", linewidth=2.0,
            label="Max 3 retries, no budget")
    ax.plot(error_rates * 100, m_jitter, color="#E69F00", linewidth=2.0,
            linestyle="-.",
            label="Max 3 retries + full jitter")
    ax.plot(error_rates * 100, m_budget, color="#009E73", linewidth=2.0,
            label="10% retry budget (cap)")
    ax.axhline(1.0, linestyle="--", color="#999999", linewidth=1.0,
               label="Baseline (no retries)")

    # Tipping-point annotation: where retries exceed 2× (doubling the load)
    # For 3 retries unlimited: e^0 + e^1 + e^2 + e^3 = 2.0 → e ≈ 0.544
    tipping_e = None
    for i, (e, m) in enumerate(zip(error_rates, m_unlimited)):
        if m >= 2.0:
            tipping_e = e
            break
    if tipping_e is not None:
        ax.axvline(tipping_e * 100, linestyle=":", color="#CC79A7", linewidth=1.2, alpha=0.8)
        ax.text(tipping_e * 100 + 0.5, 2.15, f"2× amplification\n@ {tipping_e*100:.0f}% errors",
                color="#CC79A7", fontsize=7.5)

    # Cascade zone shading (error rate > 50% — deep trouble)
    ax.axvspan(50, 90, alpha=0.06, color="#D55E00")
    ax.text(65, 3.7, "cascade\nzone", color="#D55E00", fontsize=7.5, ha="center", alpha=0.8)

    ax.set_xlabel("Server Error Rate (%)")
    ax.set_ylabel("Effective Load Multiplier")
    ax.set_title("Retry Amplification vs Server Health")
    ax.set_xlim(0, 90)
    ax.set_ylim(0.8, 4.3)
    ax.legend(loc="upper left", fontsize=8)

    # Formula annotation
    ax.text(0.97, 0.30,
            "Multiplier =\n1 + e + e² + e³",
            transform=ax.transAxes,
            ha="right", va="bottom",
            fontsize=7.5, color="#555555",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))

    fig.tight_layout()
    out_path = args.out / "retry_amplification.svg"
    fig.savefig(out_path, format="svg")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
