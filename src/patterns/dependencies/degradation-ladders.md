# Degradation Ladders

> **One-liner:** Define in advance what the service does when each dependency is unavailable — because deciding under pressure what to drop leads to inconsistent and sometimes dangerous choices.

## Symptom

Degradation ladders are a design pattern, not a failure mode. These symptoms indicate their absence:

- During incidents, heated debate about whether to disable feature X to reduce load — operators have no pre-agreed sequence to execute.
- Dependency failure causes unexpected behaviors: undocumented fallbacks, or exceptions that propagate to users as 500 errors.
- Different engineers make different degradation decisions in different incidents, leading to inconsistent user experiences and postmortems that conclude "we need a process."
- Under load shedding, the wrong traffic is shed: high-value requests dropped before low-value ones because priority is not pre-defined.

## Mechanism

A degradation ladder is a predefined ordered sequence of capability reductions, where each rung specifies:
1. **Trigger:** The condition that activates this rung (dependency X down, CPU > 80%, etc.).
2. **What drops:** Which feature or capability is disabled or degraded.
3. **User impact:** What the user observes (degraded response, missing feature, cached stale value).
4. **Capacity relief:** How much load this rung removes (useful for capacity planning).

**Example ladder for a product recommendation service:**

| Rung | Trigger | What drops | User sees | Load relief |
|------|---------|-----------|-----------|-------------|
| 1 | ML ranking service slow | Use static sort order | Slightly less relevant results | 30ms latency savings |
| 2 | ML ranking service down | Use cached ranking from 1hr ago | Stale but plausible results | Avoids all ML calls |
| 3 | Cache cluster slow | Use pre-computed defaults | Same defaults for all users | Avoids all cache calls |
| 4 | Load > 90% CPU | Shed unauthenticated requests | Logged-in users only served | 40% traffic reduction |

**Why pre-definition matters:** Under an incident at 2am, an operator making a real-time decision about which feature to disable is working under time pressure, incomplete information, and cognitive load. A pre-defined ladder converts that decision to a lookup: "We're on rung 2, activate rungs 1 and 2."

**The difference between a ladder and ad hoc degradation:** Ad hoc degradation is when code has fallback logic that no one documented, that was added when the dependency was first wired up. The fallback may be incorrect, may have bugs that haven't been exercised since it was written, and may not be known to operators. A ladder is when the fallback behavior is explicitly tested, documented, and communicated to operations.

**Rungs must be tested:** A degradation ladder that is defined but never exercised is not a ladder — it's a hope. Each rung must be:
- Implemented (the code path for each degraded mode must exist).
- Tested (the degraded mode must be exercised in staging or production regularly).
- Reversible (returning to full service from each rung must be documented and tested).

## Real-world sightings

**Amazon Web Services, "Static stability using Availability Zones."** The Builders' Library essay describes Amazon's approach to pre-defining degraded operating modes for availability zone failures. Rather than responding dynamically to an AZ failure, services are designed with explicit modes for "all AZs healthy," "one AZ degraded," and "two AZs degraded." Each mode has pre-defined behavior, not emergent behavior.

**Google SRE Book (Beyer et al., 2016).** Chapter 8 ("Release Engineering") describes feature-flagged degradation as a standard component of Google's service design. The book recommends that every non-trivial feature have a flag that can disable it, and that the set of flags be ordered by user impact — constituting an informal ladder.

## Mitigations

### Feature flags for each rung

**What it is:** Each rung is implemented as a feature flag that can be toggled in real time without a deploy. The ladder is encoded as an ordered list of flags that operators execute in sequence.

**Cost:** Every feature on the ladder must be flag-gated, adding code complexity. Flag state must be persisted somewhere reliable (that doesn't depend on the services being degraded).

**How it backfires:** Feature flags that have never been activated in production may have bugs that surface during incidents — exactly when debugging capacity is lowest. Test each flag periodically in production (dark launches, load tests with flags activated).

### Automatic rung activation via thresholds

**What it is:** Instrument each trigger condition; automatically activate the corresponding rung when the threshold is crossed, without requiring operator action. Report the activation to operators.

**Cost:** Automatic degradation can hide failures that should be investigated rather than automatically absorbed. Requires confidence that the automation is correct.

**How it backfires:** A threshold miscalibrated to activate too easily causes automatic degradation during normal variance, surprising users and operators with unrequested feature reductions.

### Operator runbooks per rung

**What it is:** For each rung, maintain a runbook that describes: how to activate the rung, how to verify it is active, what the user impact is, how to monitor whether it is helping, and how to return to the previous rung.

**Cost:** Runbooks require maintenance as the system evolves.

**How it backfires:** Stale runbooks (that don't reflect current flag names, service endpoints, or procedures) are worse than no runbooks — they send operators in the wrong direction under pressure.

## Interactions

- [Criticality Tiers](criticality-tiers.md) — tier assignment drives which dependency's failure activates which rung.
- [Load Shedding](../overload/load-shedding.md) — load shedding is typically a high rung on the ladder (significant user impact, significant capacity relief).
- [Correlated Failure](correlated-failure.md) — a correlated failure may activate multiple rungs simultaneously; the ladder must define behavior when multiple triggers fire.

## References

- Amazon Web Services. "Static stability using Availability Zones." *AWS Builders' Library*.
  Section on pre-defined degraded modes is the practical foundation for the ladder pattern.
- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 8 covers feature flags as degradation infrastructure; Chapter 12 covers on-call runbooks.
- Kleppmann, M. *Designing Data-Intensive Applications*. O'Reilly, 2017.
  Chapter 12 discusses graceful degradation in the context of end-to-end system design.
