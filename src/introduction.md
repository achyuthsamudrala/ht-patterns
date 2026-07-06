# Introduction

This is a field guide for engineers who build, operate, or debug high-throughput, low-latency distributed services — including LLM inference serving.

## Who this is for

Engineers who already know how to build services and are hitting the problems that appear only at scale: latency percentiles that behave unexpectedly, capacity that doesn't scale linearly, caches that turn from assets into liabilities, and failures that don't go away when the trigger clears.

This guide assumes you are comfortable reading latency histograms, understand what a p99 is, and have written at least one service that queues work. It does not assume prior experience with queuing theory or formal systems analysis — that theory is introduced where needed, in the context of the pattern it explains.

## What this guide is not

This is not a textbook on distributed systems design. It covers a specific set of failure modes and their mitigations. It does not cover consensus protocols, data consistency, deployment infrastructure, or the dozens of other concerns in production systems. Those are well-covered elsewhere.

It is also not a comprehensive survey of every technique in the literature. The patterns included are those that appear repeatedly in incident postmortems, appear in the SRE and distributed systems literature, or were observed in production systems by contributors. Selection bias toward patterns that bite engineers in practice is intentional.

## Two reading modes

**Design mode** — read a pattern before you build. Each page describes the trap you are trying to avoid and the mitigations available, including how each mitigation backfires under specific conditions.

**Incident mode** — start at the [Symptom Index](symptom-index.md). Find your observable, follow 2–4 candidate patterns, read the Mechanism section of the one that fits.

## How patterns are structured

Every page follows the same six-section template:

1. **Symptom** — what your dashboards show, written for someone mid-incident.
2. **Mechanism** — why it happens, with the minimum theory needed to reason about it.
3. **Real-world sightings** — documented incidents, traceable to public sources. No fabricated examples.
4. **Mitigations** — what to do, what it costs, and **how it backfires** under specific conditions.
5. **Interactions** — which other patterns compound with this one and why.
6. **References** — 3–7 items, annotated.

The "how it backfires" entries matter. Most incidents involving mitigations aren't "the mitigation failed to prevent the problem" — they're "the mitigation worked as designed but the design assumptions were wrong." Reading the failure modes of your mitigations is as important as reading the mitigations themselves.

## Where to start

- If something is on fire right now: [Symptom Index](symptom-index.md)
- If you want the underlying math before reading patterns: [Foundations](foundations/littles-law.md)
- If you want to understand how patterns combine: [Interaction Map](interaction-map.md)
- If you're building inference serving infrastructure: [Inference patterns](patterns/inference/index.md)

## A note on real-world sightings

Each pattern page includes a "Real-world sightings" section. The standard for these entries is verifiable public sources: peer-reviewed papers, published engineering blog posts, or official documentation. Incidents described in these sections happened and were reported publicly.

Where no strong public sighting exists, the section says so in one sentence rather than fabricating a plausible-sounding incident. The absence of a cited sighting does not mean the pattern is theoretical — it means no public documentation was found.
