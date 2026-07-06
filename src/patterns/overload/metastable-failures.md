# Metastable Failures

> **One-liner:** The system reaches a bad state that it cannot exit on its own — a feedback loop sustains the failure even after the original trigger is gone.

## Symptom

- The trigger is gone but the service hasn't recovered.
- Load returns to normal; error rate stays elevated.
- Restarting servers makes it worse: new instances are cold, overloading survivors while they warm up.
- Cache hit rate low; backend load high — backends too overloaded to serve the reads that would warm the cache.
- The system oscillates: brief partial recovery followed by another collapse, repeatedly.
- Recovery requires human intervention: request draining, retry disabling, cache prewarming, or traffic shedding.
- On-call finds no active trigger in the timeline — the incident is "sustaining itself."

## Mechanism

A metastable failure has three necessary components:

**1. A good state that is not globally attracting.** The system works well at normal load but requires that load to stay within a region. Once outside that region, it cannot return on its own.

**2. A trigger that moves the system out of the good state.** A load spike, a restart, a cache flush, a configuration change. The trigger may be brief — a few seconds of traffic burst.

**3. A sustaining mechanism that keeps the system out of the good state.** This is the defining property. Without a sustaining mechanism, the system recovers when the trigger ends. With one, the bad state becomes self-maintaining.

The formal model (Brooker et al., HotOS '21) shows that a system can have two stable equilibria: a good equilibrium at normal load and a bad equilibrium under overload. The system is "metastable" in the sense that it's stable in the bad state but cannot transition back to the good state without external help.

**Common sustaining mechanisms:**

*Retry amplification:* Failed requests generate retries, multiplying load. Higher load causes more failures, generating more retries. The loop sustains the overload even after the original traffic drops. See [Retry Storms](retry-storms.md).

*Cold-cache load amplification:* A cache restart empties the cache. All requests become misses. Backends are not provisioned for 100% miss traffic; they become overloaded. Overloaded backends respond slowly or fail, so cache fill reads fail, the cache stays cold, and all requests continue missing. See [Cache as Hard Dependency](../caching/cache-as-hard-dependency.md).

*Resource leak under stress:* Some systems leak resources (connections, threads, file descriptors) faster under load than they reclaim them. Once the leak crosses a threshold, available resources fall, latency increases, more resources are consumed waiting, and the leak accelerates.

*GC pressure:* Under high load, allocation rate rises. GC runs more frequently and causes stop-the-world pauses. During pauses, requests queue. The burst of queued requests after the pause causes another GC, sustaining elevated latency.

The shared structure: the sustaining mechanism takes load that would naturally decrease (as the trigger passes) and keeps it elevated. The system is stable in the bad state as long as the mechanism is active.

## Real-world sightings

**Brooker et al., "Metastable Failures in Distributed Systems" (HotOS '21).** The paper introduces the formal framework and provides several production-derived case studies, including a cache-restart scenario that matches the cold-cache sustaining mechanism exactly, and a retry-driven scenario where retries from a partial outage sustained load after the original trigger cleared. The authors note that the defining feature of metastable failures is that incident timelines show no active cause at the time the failure is occurring — the cause was in the past.

**Brooker et al., "Metastable Failures in the Wild" (OSDI '22).** The follow-up study of production incidents across multiple services classifies failures by sustaining mechanism. Cache-related metastable failures (cold restart, hot key expiry) and retry-related failures are identified as the two most common categories. The paper provides design principles for preventing and escaping metastable failures, including: bounded retry rates, admission control that accounts for feedback, and recovery procedures that address the sustaining mechanism directly (not just the trigger).

## Mitigations

### Retry budgets and backoff

**What it is:** Cap the total retry rate across a fleet; require exponential backoff with jitter. See [Retry Storms](retry-storms.md) for implementation details.

**Cost:** Some requests that could succeed with a retry are not retried.

**How it backfires:** Per-client budgets sum to N × budget for a fleet of N clients. Fleet-level enforcement requires coordination. Budgets don't help if the sustaining mechanism is not retry-based.

### Cache warmup before traffic

**What it is:** After any cache restart, run a prewarming phase that populates hot keys from snapshots or background reads before routing production traffic.

**Cost:** Delays recovery; requires maintaining a warm-key corpus or snapshot mechanism.

**How it backfires:** The warmup corpus may not reflect current access patterns. If warmup takes longer than client timeout windows, the service appears down for the entire warmup duration.

### Admission control during recovery

**What it is:** When recovering from a sustained overload, explicitly rate-limit admitted requests to below capacity, allowing the backlog to drain and the sustaining mechanism (cache filling, resource reclaim) to complete before accepting full load.

**Cost:** Extended recovery period; requires an operator decision to enable.

**How it backfires:** Setting the throttle too aggressively extends downtime. Setting it too loosely allows the sustaining mechanism to re-engage before recovery completes.

### Circuit breakers

**What it is:** Detect when a downstream dependency is failing and stop sending traffic to it, allowing it to recover behind the circuit breaker.

**Cost:** Requests that depend on the broken dependency fail fast. Requires defining a fallback behavior.

**How it backfires:** A circuit breaker that re-closes too quickly (short half-open window) allows a recovering dependency to be immediately re-overloaded by the released traffic. The breaker must hold long enough for the sustaining mechanism to clear.

## Interactions

- [Retry Storms](retry-storms.md) — the most common sustaining mechanism. Retries are what prevent the system from recovering once the trigger passes.
- [Cache as Hard Dependency](../caching/cache-as-hard-dependency.md) — cold cache is the second most common sustaining mechanism.
- [Goodput Collapse](goodput-collapse.md) — collapse is the state the system is stuck in; metastability is why it stays there.
- [Cold Restart Warmup](../caching/cold-restart-warmup.md) — the specific recovery procedure that must succeed for cache-related metastable failures to resolve.

## References

- Brooker, M. et al. "Metastable Failures in Distributed Systems." *HotOS 2021*.
  Introduces the formal model; defines the sustaining mechanism concept. Essential reading for any distributed systems practitioner.
- Brooker, M. et al. "Metastable Failures in the Wild." *OSDI 2022*.
  Production case studies classified by sustaining mechanism. Section 4 covers design principles for prevention; Section 5 covers recovery.
- Nygard, M. *Release It!* 2nd ed. Pragmatic Programmers, 2018.
  Chapters 4–6 cover stability patterns including circuit breakers, timeouts, and bulkheads as tools for preventing metastable states.
