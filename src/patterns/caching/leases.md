# Leases

> **One-liner:** A lease serializes cache population: only the token holder may write the new value, and all other misses get a signal to wait or use stale data — replacing N simultaneous backend fetches with one.

## Symptom

Leases are a mitigation, not a failure mode. The symptoms driving their adoption are those of [Stampede and Coalescing](stampede-and-coalescing.md):

- Periodic backend load spikes that align with cache expiry events.
- Multiple hosts simultaneously fetching the same key from the origin on a miss.
- Write-on-miss races causing stale data to persist: a reader gets a cache miss, fetches from the origin, and writes back — racing with another reader doing the same thing.

Leases are specifically the right tool when:
- The cache is distributed (multiple app hosts share one cache cluster).
- Single-flight / in-process coalescing is not sufficient (it coalesces within one host but not across hosts).
- Write-on-miss races cause stale data to persist (read-your-writes violation).

## Mechanism

A lease is a token issued by the cache server to the first client that encounters a miss for a given key. The token grants the right to write the key's new value. All other clients that miss the same key either:
1. Receive a "wait" signal — they retry after a short delay, at which point the cache is likely warm.
2. Receive a stale copy (if the cache holds an expired value) — this is the "stale-while-revalidate" variant.

The token is invalidated when either:
- The holder writes the new value (success path).
- The holder's request times out or the lease TTL expires (error path); the lease is released for another client.

**Why it's stronger than single-flight:** In a multi-host deployment, single-flight collapses misses within one host. With 100 hosts, you still get 100 backend requests on a popular miss (one per host). Leases run in the cache cluster, not the application layer, so they coalesce across all hosts for the same key: one backend request regardless of host count.

**The write-invalidation variant:** Facebook uses leases in a second scenario — write invalidation under concurrent misses and sets. When a write is made to the origin (updating user data), the cache key is invalidated. If a read race begins before the write completes, the reader may fetch a pre-write value from the origin and write it back, perpetuating stale data. A lease on the invalidated key prevents any reader from writing back until after the write-originating invalidation completes.

**Token lifecycle:**
1. Client A GETs key K → miss → cache issues lease token T for K, returns miss + token.
2. Client A fetches value V from origin using token T.
3. Client B GETs key K → miss → cache returns "wait" (lease in flight).
4. Client A SETifToken(K, V, T) → cache accepts (token matches), sets K=V, invalidates lease.
5. Client B retries GET K → hit → returns V.

If Client A fails (request timeout):
- Lease TTL expires → cache releases K's lease.
- Client C GETs K → miss → gets new lease → fetches fresh value.

## Real-world sightings

**Nishtala et al., "Scaling Memcache at Facebook" (NSDI 2013).** The lease mechanism is the central technical contribution of Section 3.2. Facebook introduced leases to address two production problems: (1) thundering herd on popular key expiry, and (2) stale sets from concurrent write-invalidation races. The paper reports that leases reduced DB query rates significantly during cache-population periods and eliminated the race condition that previously caused stale data to persist after writes.

**Memcached "add" command as a primitive lease.** Memcached's `add` command (set only if key doesn't exist, atomically) has been used as a lightweight lease primitive before the formal lease extension: on a miss, the first client calls `add(lock_key, ...)` to claim the right to populate the value. Other clients that find `lock_key` set wait. This is a common pattern in Memcached-based systems that predates the formal lease API.

## Mitigations

### Stale-on-hold

**What it is:** When a lease is held by another client, return the stale (expired) value to waiting clients rather than making them wait. Clients see slightly out-of-date data for the duration of one revalidation cycle but experience no latency increase.

**Cost:** Requires the cache to retain the expired value until the lease is resolved. Increases cache memory footprint for hot keys.

**How it backfires:** For data where staleness is unacceptable (financial, inventory), stale-on-hold is not a valid option. The caller must explicitly declare freshness requirements.

### Lease timeout with back-off

**What it is:** If the lease holder doesn't complete within a timeout (e.g., 10ms), the cache releases the lease and allows another client to try. Clients waiting for a lease use exponential back-off before retrying.

**Cost:** Lease timeout must be tuned to be longer than normal backend latency.

**How it backfires:** A lease timeout shorter than backend p99 latency releases the lease while the first holder is still working, causing a second backend request to begin in parallel — defeating the lease's purpose.

### Write-invalidation with lease hold

**What it is:** On cache invalidation due to a write, hold any leases until the write has propagated. Readers get stale data (or wait) until the write is confirmed at the cache, preventing the stale-set race.

**Cost:** Adds latency to reads that happen to land during a write invalidation window.

**How it backfires:** If the write path fails to release the lease hold (e.g., the writer crashes), the lease hold persists until it times out, blocking population of the key.

## Interactions

- [Stampede and Coalescing](stampede-and-coalescing.md) — leases are the distributed version of request coalescing; both solve the same thundering herd problem.
- [Cache as Hard Dependency](cache-as-hard-dependency.md) — a cache cluster that correctly handles leases still exhibits the cache-down load multiplier if the cache is down.
- [Slow Cache vs. Down Cache](slow-cache-vs-down-cache.md) — a slow lease resolution (cache slow) is more dangerous than a fast miss (cache down), because clients accumulate waiting on the lease.

## References

- Nishtala, R. et al. "Scaling Memcache at Facebook." *NSDI 2013*.
  Section 3.2 is the authoritative description of the lease mechanism; Section 3.3 covers the write-invalidation variant.
- Fitzpatrick, B. "Distributed Caching with Memcached." *Linux Journal*, 2004.
  Background on Memcached primitives; explains the `add` command as a primitive lease.
