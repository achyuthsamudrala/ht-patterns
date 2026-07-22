# Read/Write Splitting

> **One-liner:** Routing reads to replicas multiplies read capacity, but every replica is a separate, independently-lagging copy of the truth — the split only works if the routing decision knows how stale each query can tolerate, not just whether it's a SELECT.

## Symptom

- The same request pattern returns different data depending on which replica happens to serve it.
- Adding more read replicas doesn't reduce staleness complaints, even though per-replica load drops.
- A user's own write isn't visible on the very next read, but is visible on a later one.
- Read-after-write bugs cluster in flows with an immediate read following a write in the same request (redirect-after-POST, submit-then-list-again).
- The proxy or driver treats all replicas as interchangeable for routing purposes; there's no per-query signal for "this one needs to be fresh."

## Mechanism

A read/write splitting layer — a proxy (ProxySQL, PgBouncer combined with a router, Vitess's VTGate) or a smart client driver — inspects each statement and routes writes (and, depending on configuration, anything inside a transaction that contains a write) to the primary, while routing standalone reads to a pool of replicas. This is attractive because reads usually dominate write volume, so multiplying read capacity across replicas removes the primary as the read bottleneck.

The routing decision, though, is made purely on statement shape (SELECT vs. everything else), not on the data's actual consistency requirement. Two SELECTs that look identical to the router can have opposite freshness needs: rendering a public, rarely-changing profile page tolerates seconds of staleness; checking a just-submitted payment's status does not. Splitting by statement type conflates these.

**Granularity matters.** Some proxies route at the statement level (each SELECT independently chooses a replica); others route at the transaction level (the first statement's type decides the whole transaction's target). Statement-level routing is more efficient but breaks read-your-writes within a single logical operation if a write and a dependent read are issued as separate statements rather than one transaction. Transaction-level routing fixes that but over-routes: an ORM that opens an implicit transaction for a single read now sends that read to the primary unnecessarily.

**Sticky routing** — keeping a client pinned to the primary or a specific replica for some window after a write — is the common fix, but it reduces the very read-scaling benefit the split was meant to provide (see [Replication Lag](replication-lag.md)).

## Real-world sightings

**Vitess.** Vitess (originally built at YouTube, now the basis of PlanetScale) implements read/write splitting as a first-class routing concept: tablets are typed `PRIMARY` or `REPLICA`, and VTGate routes queries by tablet type, with explicit support for pinning a session to the primary after a write when the application requests read-your-writes semantics. The documented need for this override is itself evidence that statement-shape routing alone is insufficient.

**ProxySQL.** ProxySQL's query rules engine is widely used in the MySQL ecosystem specifically to implement read/write splitting via regex-matched routing rules, with documented guidance that transactions must be routed as a unit to the writer once any write is detected, to avoid a read within the same transaction hitting a lagging replica.

## Mitigations

### Explicit per-query consistency annotation

**What it is:** Instead of inferring routing from statement type, have the application declare per-request whether it needs fresh data (route to primary or a lag-bounded replica) or can tolerate staleness (route to any replica).

**Cost:** Requires discipline across every code path that issues queries; easy to get wrong by omission.

**How it backfires:** The path of least resistance for a developer in a hurry is to mark everything "can be stale," since that's what makes the read succeed without extra plumbing — which silently reintroduces staleness for queries that actually needed freshness.

### Sticky routing to primary after a write

**What it is:** Pin a session or user to the primary for a fixed window after any write it issues.

**Cost:** The primary absorbs more read load, concentrated right after write bursts when it's already busiest.

**How it backfires:** Users or services that write frequently effectively never read from replicas, defeating the scaling purpose for the exact traffic that motivated the split.

### Transaction-aware routing

**What it is:** Detect the first write in a transaction and route the entire transaction — including prior and subsequent reads in the same transaction — to the primary.

**Cost:** Requires the proxy or driver to buffer or peek at statements to detect a write before committing to a route, and over-routes read-only transactions that happen to be opened in write-capable mode.

**How it backfires:** ORMs that wrap simple reads in an implicit transaction (common default behavior) unnecessarily load the primary for queries that never write.

### Lag-bounded replica selection

**What it is:** Combine routing with the lag-aware eviction described in [Replication Lag](replication-lag.md) — only route to replicas within an acceptable staleness bound for the query's declared tolerance.

**Cost:** Under a lag spike, the eligible replica pool for freshness-sensitive queries can shrink to zero, forcing a fallback to the primary.

**How it backfires:** Same failure mode as lag-aware routing generally: correlated lag across all replicas removes the entire fallback pool at once.

## Interactions

- [Replication Lag](replication-lag.md) — the root cause that makes read/write splitting a staleness decision rather than a free scaling lever.
- [Connection Pool Exhaustion](connection-pool-exhaustion.md) — splitting reads across replicas multiplies the number of connection pools that must each stay within the database's connection ceiling.
- [Algorithms Under Stress](../load-balancing/algorithms-under-stress.md) — replica selection is itself a load-balancing problem, but weighted by staleness tolerance rather than by load alone.

## References

- Vitess documentation. **"Query Serving"** and **"VTGate."** https://vitess.io/docs/
  Describes tablet-type-based routing and the primary-pinning override for read-your-writes.
- ProxySQL documentation. **"Query Rules."** https://proxysql.com/documentation/
  Canonical reference for regex-based read/write split routing in the MySQL ecosystem.
- Kleppmann, M. **Designing Data-Intensive Applications.** O'Reilly, 2017.
  Chapter 5 frames read/write splitting as a tradeoff between read scalability and the specific consistency guarantees (read-your-writes, monotonic reads) that break under naive splitting.
