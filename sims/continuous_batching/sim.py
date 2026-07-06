#!/usr/bin/env python3
"""
Continuous batching simulation.

Compares static batching vs continuous (iteration-level) batching for LLM serving.

Two-panel figure:
  1. TTFT distribution — static vs continuous
  2. Tokens-per-step throughput over time — shows static batch idle time vs continuous high utilization

Usage:
    python sim.py --out ../../src/figures/continuous_batching

Output:
    continuous_batching.svg
"""
import argparse
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt

RNG = np.random.default_rng(42)

# ── Simulation parameters ─────────────────────────────────────────────────────
N_REQUESTS = 120                       # total requests to simulate
PREFILL_MS_PER_TOKEN = 0.10           # ms per prompt token (compute-bound)
DECODE_MS_PER_STEP = 12.0             # ms per decode iteration (memory-BW-bound)
BATCH_SIZE = 8                         # static batch size / continuous max batch


def generate_requests(n: int, rng: np.random.Generator):
    """Generate (prompt_len, output_len) pairs with realistic variance."""
    prompts = rng.integers(64, 512, size=n).tolist()
    # Heavy-tailed output distribution: mix of short (chat) and long (code/doc) completions
    short = rng.integers(20, 80, size=n)
    long = rng.integers(200, 600, size=n)
    mask = rng.random(n) < 0.3          # 30% are long responses
    outputs = np.where(mask, long, short).tolist()
    return list(zip(prompts, outputs))


def sim_static(requests, batch_size: int):
    """
    Static batching: assemble batch_size requests, prefill all, decode to
    max_output, then assemble next batch.  Returns per-request TTFT (ms) and
    per-decode-step active token count (for GPU utilization proxy).
    """
    ttfts = []
    active_per_step = []   # tokens actively decoding at each step
    t = 0.0
    i = 0
    while i < len(requests):
        batch = requests[i: i + batch_size]
        total_prompt = sum(r[0] for r in batch)
        max_output = max(r[1] for r in batch)

        # Prefill entire batch
        prefill_time = total_prompt * PREFILL_MS_PER_TOKEN
        t += prefill_time
        for j in range(len(batch)):
            ttfts.append(t)

        # Decode until longest sequence done
        alive = list(range(len(batch)))
        done_at = [r[1] for r in batch]   # output length = step at which seq finishes
        for step in range(1, max_output + 1):
            alive = [j for j in alive if done_at[j] >= step]
            active_per_step.append(len(alive))
            t += DECODE_MS_PER_STEP

        i += batch_size

    return ttfts, active_per_step


def sim_continuous(requests, max_batch: int):
    """
    Continuous (iteration-level) batching: at each decode step, completed
    sequences leave and queued requests join immediately.
    Returns per-request TTFT (ms) and per-step active token count.
    """
    ttfts = [None] * len(requests)
    active_per_step = []
    t = 0.0
    queue = list(range(len(requests)))  # indices of requests yet to be admitted
    # Each active entry: [req_idx, tokens_remaining, prompt_len]
    active = []

    while queue or active:
        # Admit from queue until batch is full (no KV budget modeled — just batch cap)
        while queue and len(active) < max_batch:
            idx = queue.pop(0)
            plen, olen = requests[idx]
            prefill_ms = plen * PREFILL_MS_PER_TOKEN
            t_first_token = t + prefill_ms
            ttfts[idx] = t_first_token
            # Prefill adds time but we absorb it as an event at admission
            # (simplified: treat prefill as instantaneous within step for clarity)
            active.append([idx, olen, plen])

        if not active:
            break

        # One decode step
        active_per_step.append(len(active))
        t += DECODE_MS_PER_STEP

        # Remove completed sequences
        active = [[i, rem - 1, p] for i, rem, p in active if rem - 1 > 0]

    return ttfts, active_per_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=Path("../../src/figures/continuous_batching"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    style = Path(__file__).parent.parent / "style.mplstyle"
    plt.style.use(style)

    requests = generate_requests(N_REQUESTS, RNG)

    s_ttfts, s_active = sim_static(requests, BATCH_SIZE)
    c_ttfts, c_active = sim_continuous(requests, BATCH_SIZE)

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, (ax_ttft, ax_util) = plt.subplots(1, 2, figsize=(10, 4.5))

    # Panel 1: TTFT distribution
    s_med = np.median(s_ttfts)
    c_med = np.median(c_ttfts)
    bins = np.linspace(0, max(max(s_ttfts), max(c_ttfts)) * 1.05, 30)
    ax_ttft.hist(s_ttfts, bins=bins, alpha=0.75, color="#E69F00",
                 label=f"Static (median={s_med:.0f} ms)")
    ax_ttft.hist(c_ttfts, bins=bins, alpha=0.75, color="#009E73",
                 label=f"Continuous (median={c_med:.0f} ms)")
    ax_ttft.set_xlabel("Time to First Token (ms)")
    ax_ttft.set_ylabel("Request count")
    ax_ttft.set_title("TTFT Distribution")
    ax_ttft.legend()
    ax_ttft.grid(True, ls="--", alpha=0.4)

    # Panel 2: active sequences per decode step (GPU utilization proxy)
    # Smooth with a short rolling window for readability
    def smooth(arr, w=5):
        return np.convolve(arr, np.ones(w) / w, mode="valid")

    s_sm = smooth(s_active)
    c_sm = smooth(c_active)
    steps_s = np.arange(len(s_sm))
    steps_c = np.arange(len(c_sm))

    ax_util.plot(steps_s, s_sm, color="#E69F00", linewidth=1.2, label="Static batching")
    ax_util.plot(steps_c, c_sm, color="#009E73", linewidth=1.2, label="Continuous batching")
    ax_util.axhline(BATCH_SIZE, color="#555555", linestyle="--", linewidth=0.8,
                    label=f"Max batch ({BATCH_SIZE})")
    ax_util.set_xlabel("Decode step")
    ax_util.set_ylabel("Active sequences (utilization proxy)")
    ax_util.set_title("Batch Utilization Over Time")
    ax_util.set_ylim(0, BATCH_SIZE + 1)
    ax_util.legend(fontsize=8)
    ax_util.grid(True, ls="--", alpha=0.4)

    # Annotate idle gaps in static batching
    idle_regions = [i for i, v in enumerate(s_active) if v < BATCH_SIZE // 2]
    if idle_regions:
        mid_idle = idle_regions[len(idle_regions) // 3]
        ax_util.annotate(
            "idle slots\n(waiting for\nlongest seq)",
            xy=(mid_idle / (len(s_active) / len(s_sm)), 1.5),
            xytext=(mid_idle / (len(s_active) / len(s_sm)) + 50, 3.5),
            fontsize=7.5, color="#E69F00",
            arrowprops=dict(arrowstyle="->", color="#E69F00"),
        )

    fig.suptitle(
        "Continuous batching: lower TTFT, higher utilization",
        fontsize=11, y=1.01,
    )
    fig.tight_layout()

    out_path = args.out / "continuous_batching.svg"
    fig.savefig(out_path, format="svg", bbox_inches="tight")
    print(f"Wrote {out_path}")
    plt.close(fig)


if __name__ == "__main__":
    main()
