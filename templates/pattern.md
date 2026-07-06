# {Pattern name}

> **One-liner:** {A single sentence stating the trap or principle.}

## Symptom

What you observe when this is happening: which graphs move, in what order, and what it
looks like in dashboards. Written for someone mid-incident.

- {Observable 1: metric, direction, and any coincident signals}
- {Observable 2}
- {Observable 3}

## Mechanism

Why it happens. The minimal theory needed — reference foundations chapters rather than
re-deriving. This is the core of the page. If a figure exists, it lives here with a
caption explaining exactly what to notice.

{Mechanism prose}

## Real-world sightings

{1–3 documented public incidents or papers. Each entry: 2–4 sentences covering what
happened, how the pattern manifested, and what the fix was. Cite a public postmortem,
paper, or engineering blog post. If no strong public sighting exists, say so in one
sentence rather than stretching a weak example.}

## Mitigations

### {Mitigation 1 name}

**What it is:** {Description}

**Cost:** {What it adds — complexity, latency, resource overhead}

**How it backfires:** {Under what conditions the mitigation makes things worse or masks
a different problem}

### {Mitigation 2 name}

**What it is:** {Description}

**Cost:** {Description}

**How it backfires:** {Description}

## Interactions

- [{Related pattern}](../path/to/pattern.md) — {One sentence on the compounding mechanism.}

## References

- {Author}. *{Title}*. {Venue/URL}, {Year}. {One line on why it's worth reading.}
