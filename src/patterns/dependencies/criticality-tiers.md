# Criticality Tiers

> **One-liner:** Not all dependencies are equal — assigning explicit tiers lets the service treat a tier-1 dependency failure differently from a tier-3 one, enabling targeted failover instead of uniform fallback.

## Symptom

Criticality tiers are a design pattern. These symptoms indicate their absence:

- All dependency failures handled the same way (full error returned to user, regardless of which dependency failed).
- A tier-3 outage (recommendation engine down) causing tier-1 behavior (write requests failing).
- During load shedding, the service sheds high-value requests before low-value ones because priority is not pre-defined.
- Operators disagree during an incident about whether a dependency is "critical" — no prior agreement exists.
- Circuit breakers configured identically across all dependencies regardless of their business impact.

## Mechanism

A criticality tier is an explicit classification of what the service can do when a dependency is unavailable. Tier assignment drives:
- **Timeout settings:** Tier-1 dependencies may warrant longer timeouts (the service really needs them); tier-3 dependencies should have short timeouts (fail fast; fallback is acceptable).
- **Circuit breaker thresholds:** Tier-3 circuit breakers can be configured to open aggressively (better to use degraded mode early); tier-1 circuit breakers need evidence of failure before opening (false positives are expensive).
- **Fallback behavior:** Tier-1 failures return an error to the user; tier-3 failures return a degraded response.
- **Alerting:** Tier-1 dependency failure pages on-call immediately; tier-3 dependency failure creates a ticket.

**Example tier assignments:**

| Dependency | Tier | Justification | Timeout | Fallback |
|-----------|------|---------------|---------|----------|
| User auth service | 1 | Cannot serve any request without it | 200ms | Hard error |
| Orders database | 1 | Write path requires it | 500ms | Hard error |
| Product catalog cache | 2 | Read path degrades without it | 50ms | Query DB directly |
| ML ranking service | 2 | Results are less relevant without it | 30ms | Static ranking |
| A/B test config | 3 | All users get control experience | 10ms | Default config |
| Analytics event sink | 3 | Missed events are acceptable | 5ms | Drop event |

**The critical vs. non-critical distinction in write vs. read paths:** A common mistake is assigning a dependency the same tier for both its read and write paths. The recommendation engine is tier-3 for read requests (degrade to static ranking) but tier-1 for the "personalized email" write path (the email cannot be sent without it). Tier assignments should be request-path-scoped, not service-scoped.

**Tier drift:** Tiers are documentation about current system behavior. As services evolve, a dependency that was tier-3 at launch may become tier-1 as features are built on top of it. Tier drift — where the documented tier diverges from the actual dependency depth — causes operators to misconfigure circuit breakers and make wrong decisions during incidents.

## Real-world sightings

**Amazon Web Services, "Using load shedding to avoid overload."** The essay describes Amazon's tiering of incoming requests (not outgoing dependencies) into criticality tiers, with load shedding configured to shed low-priority traffic first. The principle is the same: pre-classify so that automated and manual responses can be targeted.

**Google SRE Book (Beyer et al., 2016).** Chapter 20 ("Handling Overload") describes Google's system for classifying RPCs by criticality: `CRITICAL_PLUS`, `CRITICAL`, `SHEDDABLE_PLUS`, `SHEDDABLE`. These tiers determine whether the RPC is shed during overload. The tier is set by the caller at the callsite — not by the dependency — which maps to the "request-path-scoped tier" concept above.

## Mitigations

### Per-tier timeout and circuit breaker configuration

**What it is:** Define a set of default parameters for each tier (e.g., "all tier-3 dependencies get 10ms timeout and trip the circuit breaker at 5% error rate over 5 seconds"). Apply defaults by tier and override per-dependency only when justified.

**Cost:** Configuration discipline required; tiers must be documented and kept current.

**How it backfires:** Default tier-3 parameters applied to a dependency that is actually tier-1 (misclassified) causes the circuit breaker to open at normal error rates, cutting off a critical dependency during routine variance.

### Tier-aware alerting and runbooks

**What it is:** Map tier to alert severity. Tier-1 dependency failures page on-call immediately; tier-2 create high-severity tickets; tier-3 create medium-severity tickets or are logged only. The runbook for each tier-1 dependency specifies the exact fallback steps.

**Cost:** Requires maintaining alert rules aligned with tier assignments; tier changes must cascade to alert config.

**How it backfires:** Alert fatigue from tier-1 alerts on dependencies that are actually tier-2 (over-classified) causes operators to start ignoring tier-1 pages.

### Tier review in service onboarding

**What it is:** As part of integrating a new dependency, require explicit tier assignment as a reviewed decision (not a default). Record the tier, the justification, and the review in the service's runbook.

**Cost:** Adds a step to dependency onboarding.

**How it backfires:** Tiers assigned at onboarding are correct at that moment but may not be updated as the dependency is used more broadly. Regular tier reviews (e.g., quarterly) are needed.

## Interactions

- [Degradation Ladders](degradation-ladders.md) — tier assignment drives which ladder rung activates when which dependency fails.
- [Bulkheads](bulkheads.md) — pool sizes often reflect criticality: larger pools for tier-1, smaller for tier-3.
- [Load Shedding](../overload/load-shedding.md) — under load shedding, tier-3 traffic is shed first, then tier-2, then tier-1.

## References

- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 20 describes Google's RPC criticality system; the four-tier classification (`CRITICAL_PLUS`, `CRITICAL`, `SHEDDABLE_PLUS`, `SHEDDABLE`) is the canonical reference.
- Amazon Web Services. "Using load shedding to avoid overload." *AWS Builders' Library*.
  Describes tiering of incoming requests and how tiers interact with load shedding decisions.
