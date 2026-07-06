#!/usr/bin/env python3
"""
Goodput collapse simulation.

M/M/c queue with per-request deadline. Simulates how goodput (requests completing
before their deadline) collapses past the saturation point, and how the collapse
is sharper with tighter deadlines.

Usage:
    python sim.py --out ../../src/figures/goodput_collapse

Output:
    goodput_collapse.svg
"""
import argparse
import heapq
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches


def simulate_goodput_fraction(
    lam: float,
    c: int,
    mu: float,
    deadline: float,
    n_measure: int = 20_000,
    n_warmup: int = 5_000,
    seed: int = 42,
) -> float:
    """
    Discrete-event simulation of M/M/c + per-request deadline.

    Returns the fraction of arrivals (in measurement window) that complete
    before their individual deadline.

    Parameters
    ----------
    lam      : arrival rate (requests/second)
    c        : number of servers
    mu       : service rate per server (requests/second)
    deadline : time budget per request (seconds); np.inf = no deadline
    n_measure: number of arrivals to measure (after warmup)
    n_warmup : arrivals to discard for steady-state
    """
    rng = np.random.default_rng(seed)

    heap = []   # (time, event_type, payload)
    # event_type: 0 = arrival, 1 = completion (ints for fast comparison)
    q = []      # FIFO queue: (arrival_time, abs_deadline, in_measure)
    n_free = c

    n_good = 0
    n_measured = 0
    arr_count = 0
    total_arrivals = n_warmup + n_measure
    t = 0.0

    # Schedule first arrival
    heapq.heappush(heap, (rng.exponential(1.0 / lam), 0, arr_count))
    arr_count = 1

    while heap:
        t, etype, payload = heapq.heappop(heap)

        if etype == 0:  # --- arrival ---
            req_idx = payload
            in_measure = req_idx >= n_warmup
            abs_dl = t + deadline

            if in_measure:
                n_measured += 1

            # Schedule next arrival
            if arr_count < total_arrivals:
                heapq.heappush(heap, (t + rng.exponential(1.0 / lam), 0, arr_count))
                arr_count += 1

            if n_free > 0:
                n_free -= 1
                svc = rng.exponential(1.0 / mu)
                heapq.heappush(heap, (t + svc, 1, (t, abs_dl, in_measure)))
            else:
                q.append((t, abs_dl, in_measure))

        else:  # --- completion ---
            _, abs_dl, in_measure = payload
            if in_measure and t <= abs_dl:
                n_good += 1

            # Evict queue items whose deadline has already passed
            while q and t > q[0][1]:
                q.pop(0)

            if q:
                qa, qd, qm = q.pop(0)
                svc = rng.exponential(1.0 / mu)
                heapq.heappush(heap, (t + svc, 1, (qa, qd, qm)))
            else:
                n_free += 1

        # Stop once all measurement arrivals have been decided
        if n_measured >= n_measure and arr_count >= total_arrivals and not q and n_free == c:
            break

    if n_measured == 0:
        return 0.0
    return n_good / n_measured


def main() -> None:
    parser = argparse.ArgumentParser(description="Goodput collapse simulation")
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("../../src/figures/goodput_collapse"),
    )
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    c = 10           # servers
    mu = 1.0         # service rate per server (1 req/s → mean service time = 1s)
    capacity = c * mu

    # Offered loads: ρ = λ/(c·μ), sweep 0.1 to 1.8
    rho_values = np.linspace(0.05, 1.80, 60)
    lam_values = rho_values * capacity

    # Three deadline scenarios (multiples of mean service time 1/mu = 1s)
    scenarios = [
        (2.0 / mu,  "Deadline = 2× service time",  "#0072B2"),   # tight
        (5.0 / mu,  "Deadline = 5× service time",  "#009E73"),   # loose
    ]

    fig, ax = plt.subplots(figsize=(7, 4.5))

    # Reference line: ideal goodput = min(offered, capacity) [no queueing overhead]
    ideal = np.minimum(rho_values, 1.0)
    ax.plot(rho_values, ideal, "--", color="#999999", linewidth=1.2,
            label="Ideal (no deadline)")

    for deadline, label, color in scenarios:
        fractions = []
        for lam in lam_values:
            frac = simulate_goodput_fraction(lam, c, mu, deadline)
            fractions.append(frac)
        fractions = np.array(fractions)
        goodput_normalized = fractions * rho_values   # fraction × offered load
        ax.plot(rho_values, goodput_normalized, color=color, linewidth=2.0, label=label)

    # Saturation marker
    ax.axvline(1.0, linestyle=":", color="#CC79A7", linewidth=1.4, alpha=0.9)
    ax.text(1.02, 0.05, "saturation", color="#CC79A7", fontsize=8, rotation=90,
            va="bottom", transform=ax.get_xaxis_transform())

    # Collapse zone shading
    ax.axvspan(1.0, 1.80, alpha=0.05, color="#CC79A7")

    ax.set_xlabel("Offered Load  ρ = λ / (c · μ)")
    ax.set_ylabel("Goodput  (normalized to capacity)")
    ax.set_xlim(0.0, 1.80)
    ax.set_ylim(0.0, 1.15)
    ax.set_title("Goodput Collapse Past Saturation (M/M/c + deadline)")
    ax.legend(loc="upper left", fontsize=8)

    # Annotation: collapse zone
    ax.annotate(
        "Goodput collapse:\nhigh accepted RPS,\nlow completed RPS",
        xy=(1.35, 0.30),
        xytext=(1.10, 0.70),
        fontsize=7,
        color="#555555",
        arrowprops=dict(arrowstyle="->", color="#555555", lw=0.8),
    )

    fig.tight_layout()
    out_path = args.out / "goodput_collapse.svg"
    fig.savefig(out_path, format="svg")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
