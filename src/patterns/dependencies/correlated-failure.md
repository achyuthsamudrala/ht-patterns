# Correlated Failure

> **One-liner:** Redundancy provides no protection when the replicas fail for the same reason at the same time — independence in name only is not independence.

## Symptom

- Multiple independent-looking services or replicas failing simultaneously.
- Replica diversity (multiple instances, AZs, regions) providing no benefit — all fail together.
- Failure correlated with a shared deployment, config push, or underlying infrastructure event.
- Root cause traces to a single shared dependency, update, or environmental factor.
- Incident timeline shows failures starting within seconds of each other, not at random.

## Mechanism

Redundancy reduces failure probability only when replicas fail independently. If replica A and replica B share a failure domain, they fail together with probability ~1, not with probability p² (the product of independent probabilities).

**Sources of correlated failure:**

*Shared software version:* A bad deploy to all instances simultaneously affects all at once. The entire fleet shares the same buggy code. This is the most common source of correlated production failures at scale.

*Shared configuration:* A config push that simultaneously reaches all instances (via a shared config service, feature flag system, or Kubernetes ConfigMap rollout) can fail all instances simultaneously if the new config causes crashes or misbehavior.

*Shared physical infrastructure:* Instances on the same physical host, top-of-rack switch, power domain, or availability zone fail together when that component fails. "Three replicas across three AZs" is independent at the AZ level but correlated at the region level.

*Shared logical dependency:* All instances depend on a single database, cache, or service. When that dependency fails, all dependents fail together regardless of their physical distribution.

*Shared memory layout / resource exhaustion:* All instances run the same code version and are susceptible to the same memory leak, GC pause pattern, or file descriptor exhaustion. A slow traffic ramp exposes the bug in all instances at approximately the same time.

**The blast radius calculation:**

> Correlated blast radius = N × individual instance blast radius

Where N is the number of correlated replicas. Three instances with 33% traffic each provide no resilience against a shared-version bug: all three fail, 100% blast radius.

**Why partial correlation is often missed:** Partial correlation (e.g., two of three AZs on the same power grid) is hard to detect until the failure occurs. Auditing for correlated failure requires knowing the failure domains at each infrastructure layer — hardware, networking, power, software version, config — and checking that the redundancy strategy distributes across all of them.

**Failure domain hierarchies:**

For a service deployed with three replicas:
1. Instance-level independence: replicas on different hosts. Protects against: host failure.
2. Rack-level independence: replicas on different racks. Protects against: switch failure.
3. AZ-level independence: replicas in different AZs. Protects against: AZ failure.
4. Region-level independence: replicas in different regions. Protects against: region failure.
5. Version independence: gradual rollout with canary. Protects against: software bugs.
6. Config independence: staged config rollout. Protects against: bad config.

Each layer requires independent management. Solving layer 3 (AZ) while ignoring layer 5 (software version) means the system is protected against AZ failures but will be fully taken out by a bad deploy.

## Real-world sightings

**Brooker, M. "The Most Dangerous Phrase in Software Engineering." *brooker.co.za/blog*, 2020.** The post identifies "it's the same as what we already do" as the phrase that most often precedes correlated failures: a change that appears conservative (same code, same pattern, same infrastructure) but shares a failure domain with something that has been reliable. The post discusses how shared failure domains create correlated risk that violates independence assumptions.

**Amazon AWS summary for the July 2012 us-east-1 outage.** The AWS detailed service health summary describes how an Elastic Load Balancer configuration change rolled out simultaneously to all ELBs in a region, causing correlated failures across services that had independent ELBs. The correlated failure mode was the shared config deployment — the "independence" of each ELB was illusory because they all received the same configuration change at the same time.

## Mitigations

### Staged rollouts with version heterogeneity

**What it is:** Deploy new code to a fraction of instances (canary) before rolling to the fleet. Maintain a mixed-version fleet during the rollout window. If the canary shows elevated error rates, stop the rollout before the bug reaches the rest of the fleet.

**Cost:** Requires versioning infrastructure; services must tolerate running mixed versions simultaneously. Rollout takes longer.

**How it backfires:** Bugs that only manifest at scale (e.g., memory leaks that fill over hours) or under specific traffic patterns (e.g., only on traffic spikes) may not appear in canary evaluation windows, reaching the full fleet before the bug is visible.

### Multi-zone deployment with independent config paths

**What it is:** Distribute instances across AZs or regions AND ensure that config rollouts are also staged across zones. A config change goes to AZ-1 first; only after AZ-1 is stable does it roll to AZ-2 and AZ-3.

**Cost:** Config rollout latency increases. Operators must track config version per zone.

**How it backfires:** Config changes that are time-sensitive (e.g., disabling a feature during an incident) are delayed by staged rollout, requiring override mechanisms that bypass staging.

### Shuffle sharding for tenant isolation

**What it is:** Assign each tenant to a subset of resources chosen randomly (a "shard" of the fleet). Different tenants get different subsets. A correlated failure affecting one shard affects only the tenants on that shard.

**Cost:** Routing complexity; shard assignment must be maintained.

**How it backfires:** A large-enough correlated failure (e.g., fleet-wide bad deploy) still affects all shards. Shuffle sharding limits blast radius for small correlated failures (a minority of instances), not total correlated failures.

## Interactions

- [Degradation Ladders](degradation-ladders.md) — a correlated failure may activate multiple ladder rungs simultaneously; the ladder must define behavior when multiple triggers fire.
- [Bulkheads](bulkheads.md) — bulkheads prevent correlation within a service (slow dependency A affecting dependency B); this pattern addresses correlation across redundant instances.
- [Metastable Failures](../overload/metastable-failures.md) — a correlated failure that partially recovers may leave the system in a metastable state where the recovery sustaining mechanism prevents full restoration.

## References

- Brooker, M. "The Most Dangerous Phrase in Software Engineering." *brooker.co.za/blog*, 2020.
  Discusses correlated risk through shared failure domains; one of the clearest treatments of why redundancy fails.
- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 26 covers redundancy and correlated failure; the failure domain hierarchy is described in the context of SRE practice.
- Amazon Web Services. "Avoiding fallback in distributed systems." *AWS Builders' Library*.
  Discusses how shared failure domains in "fallback" paths can cause correlated failures when the fallback itself fails simultaneously.
