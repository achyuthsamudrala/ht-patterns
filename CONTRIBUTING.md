# Contributing

## Opening an issue: "we hit a variant"

Use this template when you encountered a variant of a documented pattern in production:

```
**Pattern page:** [link to the relevant page]

**Symptom you observed:** What your dashboards showed, in order.

**What was different from the page:** How your situation diverged — different failure
mode, different mitigation, different interaction.

**Source:** Public postmortem, paper, or engineering blog post URL (required for
factual claims). If the sighting is from your own experience and can't be cited,
describe it generically — the author may inject it as an un-attributed operational note.
```

## Proposing a new pattern

Open an issue with:
- The symptom (observable, graph-shaped)
- The mechanism (why it happens)
- At least one public citation

New patterns land via PR after the author reviews the mechanism and citations.

## Style rules

- 800–1,600 words per pattern page.
- All sections from [templates/pattern.md](templates/pattern.md) are required.
- Mitigations must include how the mitigation backfires.
- No fabricated incidents. Every "Real-world sightings" entry links to a citable source.
- Figures only where they make a mechanism land; prose where it's sufficient.

## Editing existing pages

PRs welcome for:
- Clarifying mechanism descriptions
- Adding citations
- Correcting mitigations or their failure modes
- Updating the symptom index or interaction map

Please keep edits within the existing structure — restructuring a page is an author decision.
