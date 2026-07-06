# Load Shedding

> **One-liner:** Reject work you cannot complete rather than queue it to timeout — a fast error returned in 1ms preserves more capacity than the same request burning 30 seconds of CPU before timing out.

## Symptom

*Shedding is a mitigation, not a failure mode. These are the symptoms indicating shedding is needed:*

- [Goodput Collapse](goodput-collapse.md) is occurring: accepted RPS high, goodput low, CPU high.
- Queue depth growing without bound under sustained load.
- p99 exceeding SLO while p50 is within it (tail building up from queue depth).

*Symptoms of correctly operating load shedding:*

- Error rate rising under overload (intentional; clients see 429/503 instead of timeouts).
- CPU dropping as shedded requests are not processed.
- Goodput maintained for accepted requests while excess is shed.

*Symptoms of misconfigured shedding:*

- Error rate high under normal load (threshold too aggressive).
- Service collapses before shedding activates (threshold too loose or signal too lagging).
- Wrong traffic being shed (high-priority requests shed before low-priority).

## Mechanism

Load shedding cuts offered load at the entry point before work enters the processing pipeline. The core decision: what signal triggers shedding, and at what threshold?

**Signal options and their failure modes:**

*Queue depth:* React when the queue exceeds a bound. Leads the actual overload but requires knowing what queue depth corresponds to SLO violation. Derived from: queue_bound = drain_rate × (deadline − min_service_time).

*In-flight request count (concurrency):* React when in-flight count exceeds the concurrency limit. Tightly coupled to processing capacity. Works well for services where request cost is uniform.

*CPU utilization:* Easy to instrument but lags the actual problem. An IO-bound service can be fully saturated with CPU at 20%. See [Autoscaling Signals](../capacity/autoscaling-signals.md) for why CPU is often the wrong signal.

*Latency percentile:* Shed when p99 exceeds a threshold. Reacts to the SLO directly but introduces feedback-loop instability: shedding reduces load, latency drops, shedding stops, load rises, latency rises, repeat.

**Priority-based shedding** assigns each request a criticality tier at admission and sheds lowest-priority requests first. When shedding is not yet triggered, all traffic flows normally. At the first shedding threshold, tier-3 traffic is shed. At the second, tier-2. This maps to [Degradation Ladders](../dependencies/degradation-ladders.md) and [Criticality Tiers](../dependencies/criticality-tiers.md).

**Early vs. late shedding:** Shed at the entry point (load balancer or API gateway), not deep in the service. Late shedding — rejecting after authentication, rate limiting, and request parsing — wastes the work done before rejection. Early shedding preserves that capacity for work that will be accepted.

## Real-world sightings

**Amazon Web Services, "Using load shedding to avoid overload."** The essay describes Amazon's approach to load shedding in production services. Key point: load shedding is framed not as a failure mode to avoid but as a designed response to overload — the alternative (letting the service collapse into goodput collapse) is worse for users. The essay covers the signal hierarchy (queue depth preferred over CPU) and priority-based shedding with explicit criticality tiers.

**Google SRE Book (Beyer et al., 2016).** Chapter 22 discusses load shedding as part of the cascading failure prevention toolkit. The book recommends shedding at the service boundary closest to the source, not at internal subsystems — consistent with early shedding.

## Mitigations

### Token bucket admission at the entry point

**What it is:** Maintain a token bucket that refills at the target throughput rate. Each request consumes a token; requests that can't acquire a token are immediately rejected.

**Cost:** Requires token bucket state; adds per-request overhead.

**How it backfires:** A token bucket smooths arrivals but doesn't account for request cost variance. Cheap requests and expensive ones consume the same tokens; at the bucket limit, cheap requests may be shed while expensive ones that are already past the limit aren't.

### Concurrency-limit-based admission

**What it is:** Track in-flight request count. Reject at the entry point when the count exceeds a limit. See [Adaptive Concurrency](adaptive-concurrency.md) for the dynamic version.

**Cost:** Requires accurate in-flight tracking; limit must be tuned.

**How it backfires:** A static concurrency limit tuned at p50 service time sheds too aggressively during normal p99 service time variance.

### Degraded mode with explicit capabilities

**What it is:** Define explicit operating modes (full / degraded / minimal) and transition between them under load. In degraded mode, only tier-1 features operate; tier-2 and tier-3 return degraded responses.

**Cost:** Every feature must have a degraded-mode behavior defined; adds code paths.

**How it backfires:** Degraded mode paths that are never tested in production often have bugs that surface during incidents, compounding the failure.

## Interactions

- [Goodput Collapse](goodput-collapse.md) — shedding is the primary structural mitigation.
- [Queue Management](queue-management.md) — queue management handles items already admitted; shedding prevents them from entering.
- [Adaptive Concurrency](adaptive-concurrency.md) — adaptive concurrency provides a dynamic shedding threshold.
- [Criticality Tiers](../dependencies/criticality-tiers.md) and [Degradation Ladders](../dependencies/degradation-ladders.md) — the framework that determines which traffic to shed in which order.

## References

- Amazon Web Services. "Using load shedding to avoid overload." *AWS Builders' Library*.
  The primary practical reference; covers signal selection, priority tiers, and the argument for early shedding.
- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 22 covers load shedding as part of cascading failure prevention.
- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  Chapter 13 covers admission control policies and their effect on effective throughput.
