# Stampede and Coalescing

> **One-liner:** When a popular cache entry expires, every concurrent reader misses simultaneously and floods the origin with identical requests — coalescing collapses N identical backend fetches into one.

## Symptom

- Periodic latency spikes that align with cache TTL boundaries: every T seconds, p99 jumps sharply, then recovers once the cache is repopulated.
- Backend RPS spikes that are much larger than the cardinality of distinct keys — the same key is requested hundreds of times simultaneously.
- CPU and database connection spikes on the origin that correlate with cache miss events rather than traffic volume.
- Under high concurrency the spikes become continuous: one key expires, the spike begins; before it clears, another key expires; origin never recovers.
- In distributed caches: stampedes multiplied by the number of application hosts (each host independently misses and fires a backend request).

## Mechanism

The stampede (also called "thundering herd" in this context) has a precise trigger: a cached value shared by many concurrent readers expires, causing all in-flight readers to miss simultaneously. The problem amplifies with popularity and is independent of arrival rate — even moderate traffic produces a stampede on sufficiently popular keys.

**The math:** A key with popularity P requests/second and TTL of T seconds produces a stampede of up to P×δt requests when it expires, where δt is the window during which incoming requests find the cache empty (typically the time for one backend round-trip). For P=500 req/s and δt=20ms, that's 10 backend requests for the same key instead of 1.

**Why it's more dangerous than it looks:** The stampede requests compete for the same backend resource (same DB row, same computation). The N simultaneous requests don't finish in 1/N the time — they each incur the full backend latency, and under contention may each take longer. The response from the first request populates the cache while the other N-1 are still in-flight; those N-1 then receive responses that are immediately stale.

**The feedback loop:** Backend latency spikes under stampede load. Higher latency means δt increases. Larger δt means more requests arrive during the miss window. More requests mean higher backend load. This transient positive feedback dissipates once the cache is warm, but during the spike it can cause [Goodput Collapse](../overload/goodput-collapse.md) on the origin.

**At origin restart:** Cold restart is a special case — all cache entries are simultaneously invalid. A cold cache under production load produces stampedes on every popular key at once. See [Cold Restart Warmup](cold-restart-warmup.md).

## Real-world sightings

**Nishtala et al., "Scaling Memcache at Facebook" (NSDI 2013).** The paper describes the "thundering herd" problem at Facebook scale: when a key is deleted from Memcache (e.g., after a write), all servers that had the key cached simultaneously miss. Facebook's solution — the "lease" mechanism — is covered in [Leases](leases.md). The stampede on restart (cold cluster startup) was handled separately with the "gutter pool" approach.

**Stack Overflow engineering blog.** Stack Overflow's use of heavily cached per-question HTML fragments meant that when a popular question's TTL expired or the question was edited, a stampede of readers would all miss and trigger a full page render from the database. The fix was a "dog-pile lock": a single lease holder computes the new value; others return the stale value while waiting.

## Mitigations

### Request coalescing (single-flight)

**What it is:** When multiple requests for the same key arrive while the cache is being populated, only one backend request is issued. The other requests wait (or receive stale data) until the first completes and populates the cache.

**Implementation:** A per-key lock or in-flight map. When a miss is detected, the request acquires the key's lock and fires the backend request. Subsequent misses for the same key find the lock held and wait. When the first request completes, it populates the cache, releases the lock, and wakes all waiters.

**Cost:** Increases tail latency for waiters (they experience the full backend latency of the single in-flight request). Under normal load this is acceptable; the alternative is N backend requests instead of 1.

**How it backfires:** If the single in-flight request fails or times out, all waiters fail together. Return stale data instead when the backend is unhealthy.

### Stale-while-revalidate

**What it is:** When a cache entry's TTL expires, serve the stale value immediately while triggering a background refresh. Readers never see a miss — they always get either fresh or stale data. The staleness window is bounded by the revalidation latency.

**Cost:** Readers may get stale data for the duration of one backend round-trip after TTL expiry.

**How it backfires:** Stale-while-revalidate does not help when the data must be fresh (financial balances, inventory counts). It also doesn't help if the entry is evicted rather than expired — eviction doesn't trigger a background refresh.

### Probabilistic early expiration (jittered TTL)

**What it is:** Each reader, on a cache hit, has a small probability of voluntarily treating the entry as expired early when remaining TTL is small. The probability increases as TTL approaches zero, causing the cache to be rewarmed before the official expiry and spreading miss load across a window rather than concentrating it at the expiry instant.

**Cost:** Increases backend load slightly (voluntary early misses).

**How it backfires:** For very popular keys, even a small probability of early revalidation per request generates significant background load. The probability function must be tuned per key's popularity.

## Interactions

- [Leases](leases.md) — the Facebook lease mechanism combines coalescing and stale-on-hold; it extends coalescing to distributed multi-host environments.
- [Cache as Hard Dependency](cache-as-hard-dependency.md) — stampedes expose the degree to which a service depends on cache health.
- [Cold Restart Warmup](cold-restart-warmup.md) — cold restart is a stampede on every key simultaneously.
- [Goodput Collapse](../overload/goodput-collapse.md) — a sustained stampede on the origin can drive it into collapse.

## References

- Nishtala, R. et al. "Scaling Memcache at Facebook." *NSDI 2013*.
  Section 3.2 describes the thundering herd problem and the lease-based solution in detail.
- Kleppmann, M. *Designing Data-Intensive Applications*. O'Reilly, 2017.
  Chapter 12 discusses cache stampede mitigation patterns including stale-while-revalidate.
- Varnish Cache documentation. "Grace mode / stale-while-revalidate." https://varnish-cache.org/docs/
  The authoritative reference for stale-while-revalidate as implemented in HTTP caches.
