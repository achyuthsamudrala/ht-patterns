# Optimistic Concurrency Control

> **One-liner:** Instead of locking a row up front, optimistic concurrency control lets every transaction proceed and checks for conflict only at commit — cheap when contention is rare, but a source of retry storms concentrated on exactly the rows that are popular enough to matter.

## Symptom

- Write APIs return conflict errors (HTTP 409/412, or an application-level "stale version" error) under concurrent updates to the same record.
- The conflict rate scales with the number of concurrent writers to specific records, not with overall system load — a quiet system with one hot record can show a high conflict rate.
- A small number of records (a popular item's inventory count, a shared counter, a frequently-edited document) account for a disproportionate share of all conflict errors.
- Client-visible errors require the client to re-fetch the current value and reapply its change, and this retry loop itself shows up as extra read/write traffic on the same hot record.
- Conflict rate rises non-linearly as concurrent writers to one record increase — doubling writers more than doubles conflicts.

## Mechanism

Optimistic concurrency control (OCC), formalized by Kung and Robinson (1981), structures a transaction into three phases: a **read phase** (read data and a version marker — a version column, row timestamp, or ETag), a **validation phase** at commit time (check whether the version marker has changed since the read), and a **write phase** (commit if unchanged, reject if changed). In SQL, this is typically expressed as `UPDATE t SET ..., version = version + 1 WHERE id = ? AND version = ?`; zero rows affected means someone else committed first, and the caller must retry.

OCC assumes conflicts are rare enough that paying the cost of detecting them at commit is cheaper than paying the cost of preventing them with locks on every read. That assumption holds for most records in most workloads. It breaks down precisely for hot records: as the number of concurrent writers *N* to a single record increases, each attempt has roughly a 1/N chance of being the one that commits before someone else does, and the rest must retry. The expected number of rounds to get everyone's write through grows with *N*, and each round burns real read and write work that is entirely discarded on conflict — the work is genuinely wasted, not merely delayed, unlike a lock queue where waiting transactions do no work at all while waiting.

This produces a shape distinct from ordinary load: a hot record under OCC can generate near-total request failure with retries, even though the aggregate request rate to the whole system is unremarkable — the pathology is concentrated entirely on the popularity distribution of individual keys, the same underlying skew that drives [Hot Partitions and Sequential Keys](hot-partitions-and-sequential-keys.md).

## Real-world sightings

**Amazon DynamoDB conditional writes.** DynamoDB exposes OCC as a first-class primitive via `ConditionExpression` on `PutItem`/`UpdateItem` (commonly checking an item's version attribute or that an attribute has an expected value before applying the write). AWS's own guidance for high-throughput counters and inventory-style items explicitly warns that conditional-write contention on a single partition key under heavy concurrent writers produces a high rate of `ConditionalCheckFailedException`, and recommends the sharded-counter and atomic-increment mitigations below for exactly this reason.

**Flash-sale and limited-inventory checkout systems.** E-commerce systems that decrement a shared inventory counter using a read-check-write pattern are a widely recognized class of production incident during high-demand launches: a large number of concurrent buyers race to decrement the same row, and if the retry loop isn't rate-limited or backed off, the resulting conflict-and-retry traffic can itself become the dominant load on the database during the sale, independent of the checkout logic's own cost.

## Mitigations

### Exponential backoff with jitter on retry

**What it is:** On a version conflict, wait a randomized, increasing interval before retrying, rather than retrying immediately.

**Cost:** Adds latency to the write path specifically under contention, when latency is least tolerable.

**How it backfires:** Without a cap tied to the request's own deadline, backoff delay can exceed the caller's timeout, converting a fast conflict error into a slow timeout with no better outcome — see [Deadline Propagation](../overload/deadline-propagation.md).

### Server-side atomic operations for simple counters

**What it is:** Push a commutative update (increment, decrement, add-to-set) into a single database-side atomic operation instead of a client-side read-modify-write-with-version-check.

**Cost:** Only applies to operations that are genuinely commutative; it doesn't help when the new value depends on application logic evaluated against the old value.

**How it backfires:** Nothing — but this mitigation simply doesn't exist for the common case where the update logic is more than "add N," which is most non-counter fields.

### Sharded counters

**What it is:** Split one hot logical counter into *N* physical sub-counters; writers pick one at random (or round-robin) to increment, and reads sum across all *N*.

**Cost:** Reads become more expensive (must aggregate *N* rows) and the schema gains complexity.

**How it backfires:** If *N* is too small relative to write concurrency, the hotspot simply moves to a handful of still-hot shards rather than disappearing; if *N* is too large, read aggregation cost dominates for a counter that's read far more often than it's written.

### Pessimistic locking for known-hot records

**What it is:** Identify records with sustained high write concurrency ahead of time and route writes to them through explicit row locking instead of OCC.

**Cost:** Requires identifying hot records in advance (or detecting them dynamically) and maintaining two different write code paths.

**How it backfires:** Locking serializes all writers to that record, capping throughput at roughly 1/latency-per-write — which is worse than OCC in the (common) case where actual conflicts are less frequent than the identification heuristic assumed.

## Interactions

- [Lock Contention and Deadlocks](lock-contention-and-deadlocks.md) — the pessimistic alternative to OCC; each is better suited to a different actual conflict rate.
- [Hot Partitions and Sequential Keys](hot-partitions-and-sequential-keys.md) — a hot row under OCC is the write-conflict expression of the same key-popularity skew that causes hot partitions.
- [Retry Storms](../overload/retry-storms.md) — OCC conflict-and-retry under high concurrency to one record is a retry storm scoped to a single row rather than a whole service.

## References

- Kung, H.T. and Robinson, J.T. **"On Optimistic Methods for Concurrency Control."** *ACM Transactions on Database Systems*, 6(2), 1981.
  The original formulation of OCC's read/validate/write phases; the source of the assumption that conflicts are rare enough to detect rather than prevent.
- Amazon Web Services. **"Amazon DynamoDB Developer Guide: Conditional Writes."** https://docs.aws.amazon.com/amazondynamodb/
  Documents `ConditionExpression`-based OCC and the recommended sharded-counter pattern for hot, high-concurrency items.
