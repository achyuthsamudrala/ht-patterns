#!/usr/bin/env python3
"""
Batching curve simulation.

Shows the latency/throughput tradeoff at different batch sizes and arrival rates.

Usage:
    python sim.py --out ../../src/figures/batching_curve

Output:
    batching_curve.svg — two-panel figure: P99 latency and throughput capacity vs batch size
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

RNG = np.random.default_rng(42)

# Processing model: batch_overhead + B * per_item_ms total ms to execute a batch of B items.
# Represents: fixed kernel/call overhead amortized over the batch.
BATCH_OVERHEAD_MS = 20.0   # fixed per-batch cost (e.g. GPU kernel launch, IPC)
PER_ITEM_MS = 0.5          # marginal cost per item in the batch


def hw_throughput(batch_size: int) -> float:
    """Maximum sustainable throughput (items/s) if hardware is kept busy at this batch size."""
    processing_ms = BATCH_OVERHEAD_MS + batch_size * PER_ITEM_MS
    return batch_size / processing_ms * 1000.0


def p99_latency(batch_size: int, arrival_rate: float, n_batches: int = 10_000) -> float:
    """
    P99 latency (ms) for a stable system (arrival_rate <= hw_throughput).

    Each item waits uniformly in [0, fill_time_ms] for the batch to assemble,
    then waits the full processing time.  Returns NaN if system is overloaded.
    """
    if arrival_rate > hw_throughput(batch_size) * 1.02:
        return float("nan")  # overloaded — queue grows unboundedly
    fill_time_ms = batch_size / arrival_rate * 1000.0
    processing_ms = BATCH_OVERHEAD_MS + batch_size * PER_ITEM_MS
    rng = np.random.default_rng(42 + batch_size)
    wait = rng.uniform(0, fill_time_ms, size=batch_size * n_batches)
    return float(np.percentile(wait + processing_ms, 99))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("../../src/figures/batching_curve"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    batch_sizes = [1, 2, 4, 8, 16, 32, 64, 128]
    arrival_rates = [20, 50, 200]   # items/second

    # Okabe-Ito palette entries
    colors = ["#009E73", "#E69F00", "#CC79A7"]
    markers = ["o", "s", "^"]

    fig, (ax_lat, ax_tput) = plt.subplots(1, 2, figsize=(10, 4.5))

    # ── Panel 1: P99 latency vs batch size ────────────────────────────────────
    hw_cap = [hw_throughput(b) for b in batch_sizes]

    for idx, (rate, col, mrk) in enumerate(zip(arrival_rates, colors, markers)):
        p99s = [p99_latency(b, rate) for b in batch_sizes]
        valid_bs = [b for b, p in zip(batch_sizes, p99s) if not np.isnan(p)]
        valid_p99 = [p for p in p99s if not np.isnan(p)]
        ax_lat.plot(valid_bs, valid_p99, color=col, marker=mrk, label=f"λ={rate}/s")

    ax_lat.set_xlabel("Batch size (B)")
    ax_lat.set_ylabel("P99 latency (ms)")
    ax_lat.set_title("Fill-time penalty grows with B")
    ax_lat.set_xscale("log", base=2)
    ax_lat.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax_lat.set_xticks(batch_sizes)
    ax_lat.legend(title="Arrival rate")
    ax_lat.grid(True, which="both", ls="--", alpha=0.4)

    # Annotate: "fill-time dominates" arrow on λ=20 curve
    ax_lat.annotate(
        "fill-time\ndominates",
        xy=(16, p99_latency(16, 20)),
        xytext=(20, 500),
        fontsize=8,
        arrowprops=dict(arrowstyle="->", color="#555555"),
    )

    # ── Panel 2: Hardware throughput capacity vs batch size ────────────────────
    ax_tput.plot(batch_sizes, hw_cap, color="#0072B2", marker="D",
                 linewidth=2, label="Hardware capacity")

    for idx, (rate, col) in enumerate(zip(arrival_rates, colors)):
        ax_tput.axhline(rate, color=col, linestyle="--", linewidth=1.2,
                        label=f"λ={rate}/s")
        # mark the minimum B needed to handle this rate
        min_b = next((b for b, c in zip(batch_sizes, hw_cap) if c >= rate), None)
        if min_b is not None:
            ax_tput.axvline(min_b, color=col, linestyle=":", linewidth=0.8, alpha=0.7)

    ax_tput.set_xlabel("Batch size (B)")
    ax_tput.set_ylabel("Throughput (items/s)")
    ax_tput.set_title("Larger batches amortize overhead")
    ax_tput.set_xscale("log", base=2)
    ax_tput.xaxis.set_major_formatter(mticker.ScalarFormatter())
    ax_tput.set_xticks(batch_sizes)
    ax_tput.legend(title="", fontsize=8)
    ax_tput.grid(True, which="both", ls="--", alpha=0.4)

    ax_tput.annotate(
        f"overhead={BATCH_OVERHEAD_MS:.0f}ms\nper-item={PER_ITEM_MS:.1f}ms",
        xy=(0.62, 0.25), xycoords="axes fraction",
        fontsize=8, color="#444444",
        bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#cccccc", alpha=0.8),
    )

    fig.suptitle(
        "Batching tradeoff: amortized overhead ↑ vs fill-time latency ↑",
        fontsize=11, y=1.01,
    )
    fig.tight_layout()

    out_path = args.out / "batching_curve.svg"
    fig.savefig(out_path, format="svg", bbox_inches="tight")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
