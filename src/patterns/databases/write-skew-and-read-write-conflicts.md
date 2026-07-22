# Write Skew and Read/Write Conflicts

> **One-liner:** Snapshot isolation stops a transaction from seeing another's uncommitted writes, but it doesn't stop two transactions from reading the same snapshot and each writing a *different* row in a way that, together, breaks an invariant neither one saw broken.

## Symptom

- An invariant that should always hold — "at least one doctor on call," "account balance never negative," "no double-booked slot" — is violated in production despite every individual transaction validating it before writing.
- The violation appears only under concurrent load and is never reproducible by replaying either transaction alone against a fresh database.
- Both transactions involved ran a `SELECT` that returned data consistent with proceeding, and both committed successfully — no error, no conflict, no deadlock, nothing in the logs to flag it.
- The two transactions wrote *different* rows (not the same row), so any monitoring keyed on row-level write conflicts sees nothing unusual.
- The bug rate scales with concurrency on the specific invariant's read pattern, not with overall write volume.

## Mechanism

Snapshot isolation (and the "REPEATABLE READ" level as implemented by Postgres and several other engines) gives each transaction a consistent view of the database as of its start, and detects **write-write conflicts** — two transactions writing the same row — refusing to let both commit. What it does *not* detect, by construction, is a **read-write conflict**: transaction A reads a row that transaction B is about to write (or vice versa), where A's decision to write something else depended on that read.

The canonical example (Kleppmann, *Designing Data-Intensive Applications*, Ch. 7): a hospital requires at least one doctor on call at all times. Doctor 1 and Doctor 2 are both on call. Both request to go off call simultaneously. Each transaction: (1) counts currently-on-call doctors in its snapshot — sees 2 — (2) since 2 ≥ 2, proceeds to set itself off call, (3) commits. Both transactions read the same snapshot (count = 2), both write a *different* row (their own on-call flag), and both commit cleanly. The database never sees a write-write conflict because the two writes touch different rows. The result: zero doctors on call, an invariant violation, with no error at any point.

A closely related variant is the **phantom**: an invariant that depends on the *absence* of rows matching a predicate, not on a specific row's value. A meeting-room booking system checks "no overlapping booking exists" then inserts a new booking; two concurrent transactions can both see no overlap in their respective snapshots and both insert, producing an overlap that neither transaction's own check caught.

Only true serializability prevents this — either full two-phase locking (which serializes via [Lock Contention and Deadlocks](lock-contention-and-deadlocks.md)'s costs), or Serializable Snapshot Isolation (SSI), which tracks read-write dependencies between concurrent transactions at runtime and aborts one side of any cycle before commit.

## Real-world sightings

**PostgreSQL documentation, "13.2.3. Serializable Isolation Level."** Postgres's own documentation describes write skew explicitly, using a variant of the on-call staffing example, and states plainly that REPEATABLE READ (Postgres's snapshot isolation level) does not prevent it — only the `SERIALIZABLE` isolation level, implemented via SSI, does. This is a rare case of a database vendor's docs directly naming a class of bug their default-adjacent isolation level does not fix.

**Fekete, A. et al., "Making Snapshot Isolation Serializable" (ACM TODS, 2005) and Cahill, M. et al., "Serializable Isolation for Snapshot Databases" (SIGMOD 2008).** The former formalizes write skew and characterizes exactly which transaction schemas are vulnerable to it under snapshot isolation; the latter introduces Serializable Snapshot Isolation, the algorithm PostgreSQL's `SERIALIZABLE` level is built on. Together they are the reason this is a solved, well-understood problem with a known, shipping fix — the failure mode persists in practice mainly because applications default to weaker isolation levels without knowing what they give up.

## Mitigations

### Use SERIALIZABLE isolation for invariant-checking transactions

**What it is:** Run transactions that check a cross-row invariant under true serializability (Postgres/CockroachDB `SERIALIZABLE`, implemented via SSI), which detects the dangerous read-write dependency cycle and aborts one transaction before commit.

**Cost:** SSI must track read-write dependencies at runtime, adding overhead, and aborts transactions under contention that a weaker isolation level would have silently allowed to commit.

**How it backfires:** The abort is a visible, retryable error rather than a silent corruption — strictly better — but if the application doesn't handle serialization-failure retries, or if operators respond to "too many aborts" by simply weakening the isolation level, the original bug returns, now hidden behind a period of apparently-improved error rates.

### Explicit locking of invariant-relevant rows

**What it is:** Use `SELECT ... FOR UPDATE` on every row the invariant depends on before evaluating it, forcing the second transaction to block rather than proceed on a stale read.

**Cost:** Converts an optimistic read into a pessimistic lock, inheriting the contention costs described in [Lock Contention and Deadlocks](lock-contention-and-deadlocks.md).

**How it backfires:** The protection applies only to code paths that remember to add `FOR UPDATE`; a new query added later that reads the same invariant-relevant rows without it silently reopens the gap for that path alone.

### Materialize the invariant as data the database can constrain

**What it is:** Instead of checking a derived condition (a `COUNT` query, an absence-of-overlap scan), model the invariant as an actual row or constraint — one "on-call slot" row per shift with a `NOT NULL` foreign key, a unique constraint on a booking's time-range key — so the database's own constraint machinery enforces it.

**Cost:** Requires reshaping the schema around the invariant, which can be a larger change than adding a lock or an isolation level.

**How it backfires:** Only enforces what maps onto a constraint the database actually supports (uniqueness, foreign keys, exclusion constraints); invariants that don't reduce to one of those still need locking or serializability.

### Serialize writes to the invariant at the application layer

**What it is:** Route all writes that touch a given invariant through a single serialized stream (an actor, a queue, a single-writer process) instead of relying on the database's concurrency control.

**Cost:** Caps throughput for that invariant to whatever one serialized stream can process.

**How it backfires:** Reintroduces a single point of contention and failure — exactly what the database's own concurrency control mechanisms exist to avoid providing for free.

## Interactions

- [Lock Contention and Deadlocks](lock-contention-and-deadlocks.md) — explicit locking is the pessimistic fix for write skew, and inherits that pattern's contention costs.
- [Optimistic Concurrency Control](optimistic-concurrency-control.md) — OCC's version check catches write-write conflicts on a single row; it does not catch write skew across different rows, which is exactly the gap this pattern describes.
- [Hot Partitions and Sequential Keys](hot-partitions-and-sequential-keys.md) — materializing an invariant as a single row (e.g., one "slot" row) can itself become a hot row under concurrent access.

## References

- Kleppmann, M. **Designing Data-Intensive Applications.** O'Reilly, 2017.
  Chapter 7 covers write skew and phantoms in depth, including the on-call doctors example this page is drawn from.
- Fekete, A. et al. **"Making Snapshot Isolation Serializable."** *ACM Transactions on Database Systems*, 30(2), 2005.
  Formalizes write skew and characterizes which transaction patterns are vulnerable under snapshot isolation.
- Cahill, M., Röhm, U., and Fekete, A. **"Serializable Isolation for Snapshot Databases."** *SIGMOD 2008*.
  Introduces Serializable Snapshot Isolation (SSI), the algorithm behind PostgreSQL's `SERIALIZABLE` level.
- PostgreSQL Documentation. **"13.2.3. Serializable Isolation Level."** https://www.postgresql.org/docs/current/transaction-iso.html
  The vendor's own explanation of write skew and why `REPEATABLE READ` does not prevent it.
