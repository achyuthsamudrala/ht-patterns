# Cold Restart Warmup

> **One-liner:** A service that restarts with an empty cache faces a guaranteed stampede on every popular key simultaneously — and origin throughput at full load without any cache buffering.

## Symptom

- Database or origin CPU spikes to 100% immediately after application restart, even before the restart completes.
- Application server latency extremely high (10–100× normal) for 5–15 minutes following a deploy or restart.
- Cache hit rate at 0% at restart, rising gradually over minutes as the cache warms organically.
- Recovery looks like a cascading failure: origin overloaded → application timeouts → retry storms → origin more overloaded.
- Scheduled restarts (rolling deploys, node replacements) consistently degrade service quality for minutes after each restart.

## Mechanism

A cache warms organically when requests arrive, miss, fetch from origin, and populate the cache. Organic warming means the cache is empty for every request until that key has been seen at least once.

Under production traffic load L:
- Normal operations: cache hit rate H means (1−H) × L requests reach the origin.
- Cold start: cache hit rate = 0 means L requests reach the origin — the full load without any cache shielding.

For a service with H=0.90 (90% hit rate), cold restart causes a 10× load multiplier on the origin relative to steady state. The origin, which was sized for 0.1L origin requests per second, now receives L.

**The compounding sequence:**
1. Restart begins; cache is empty.
2. First requests arrive; all miss; all go to origin.
3. Origin saturated; latency increases.
4. Application requests timeout waiting for origin.
5. Clients retry (see [Retry Storms](../overload/retry-storms.md)), multiplying origin load.
6. Application instances restart (health check failures from timeouts).
7. Restarted instances have empty caches; cycle accelerates.

**Why rolling deploys help but don't solve it:** A rolling deploy restarts one instance at a time, keeping other instances (with warm caches) running. However, each restarted instance starts cold and must warm independently. Under high traffic, even one cold instance can send significant load to the origin before its cache warms.

**The shared vs. per-instance cache distinction:** A shared distributed cache (Memcached, Redis) is not cold-restarted when application instances restart. But a per-instance in-process cache (or when the cache cluster itself is restarted) is cold.

## Real-world sightings

**Nishtala et al., "Scaling Memcache at Facebook" (NSDI 2013).** The paper describes the "cold cluster startup" problem: when a new Memcache cluster is brought online (e.g., in a new data center), it starts cold, but production traffic is immediately routed to it. Facebook's solution was the "gutter pool" — initially, misses from the cold cluster fell through to a warm pool that absorbed the load while the new cluster warmed up.

**Amazon Web Services, "Avoiding cache stampede."** The Builders' Library article describes the cold-start problem as a special case of the cache stampede pattern. The recommendation for cache-heavy services is to pre-warm the cache before routing traffic — either by loading known-hot keys explicitly or by replaying a sample of recent production traffic offline before the restart completes.

## Mitigations

### Pre-warming from snapshot

**What it is:** Before bringing a restarted service instance online, replay a sample of recent production requests (or load known-hot keys) against its local cache. Only add the instance to the load balancer after hit rate reaches a target (e.g., 70% of steady-state hit rate).

**Cost:** Adds latency to deploy cycles. Requires a capture mechanism for recent access patterns (request log, cache dump, or explicit hot-key list).

**How it backfires:** Replaying recent traffic only warms keys that were recently popular. Keys that are seasonally hot may not appear in the recent access log and will still cause misses.

### Traffic ramping (gradual load increase)

**What it is:** After restart, bring the new instance up behind the load balancer at low weight (1–5% of traffic). Allow the cache to warm before increasing the weight. Gradually ramp to 100% over minutes as hit rate rises.

**Cost:** Requires load balancer support for per-instance weights. Slows deploy cycles.

**How it backfires:** Under a rolling deploy with many instances, if each instance takes minutes to ramp up, the deploy window extends. If the restart is for a critical bug fix, slow ramping delays mitigation.

### Shared distributed cache with pre-populate API

**What it is:** Use a shared distributed cache (not per-instance) that persists across application restarts. For the shared cache itself (e.g., a full Redis cluster restart), expose a pre-populate script that loads a priority-ordered list of hot keys from the origin before traffic is routed to the cold cluster.

**Cost:** Hot-key list must be maintained and kept current. Pre-populate script must have controlled throughput to avoid overloading the origin.

**How it backfires:** Pre-population from a hot-key list populates based on historical access, not current demand. If access patterns shift, the hot-key list lags.

## Interactions

- [Stampede and Coalescing](stampede-and-coalescing.md) — cold restart is a stampede on every key simultaneously; single-flight coalescing helps per-key but cannot protect the origin from simultaneous misses across all keys.
- [Cache as Hard Dependency](cache-as-hard-dependency.md) — cold restart reveals the full magnitude of cache dependency: the origin load at steady state is 1/(1−H) times the origin load post-restart.
- [Retry Storms](../overload/retry-storms.md) — the cold-start origin overload drives error rates up; client retries compound into the retry storm pattern.
- [Metastable Failures](../overload/metastable-failures.md) — cold restart under load can drive the system into a metastable failure state if retry storms prevent the cache from warming.

## References

- Nishtala, R. et al. "Scaling Memcache at Facebook." *NSDI 2013*.
  Section 3.5 describes the cold cluster startup problem and the gutter pool mitigation.
- Amazon Web Services. "Avoiding cache stampede." *AWS Builders' Library*.
  Covers cold-start as a form of stampede; recommends pre-warming and traffic ramping.
