# Lock Contention and Deadlocks

> **One-liner:** Two transactions each hold a lock the other needs; without a consistent acquisition order, the database eventually detects the cycle and kills one transaction to break it — anywhere else in the call stack, that shows up as a write that mysteriously failed.

## Symptom

- Write-path p99 latency spikes with deadlock error codes (MySQL `1213`, Postgres `40P01`) or lock wait timeout errors in application logs.
- Contention concentrates on specific tables or rows during peak write hours, correlating with a known access pattern (e.g., a shared counter, a parent row referenced by many children).
- A single long-running transaction — often one doing an unrelated slow operation, like an external HTTP call, inside an open transaction — blocks unrelated short writes to the same rows.
- Lock wait time graphs show a sawtooth pattern that correlates with scheduled batch jobs or reports running against production tables.
- Reducing the isolation level or removing a range query from a transaction immediately reduces deadlock rate, pointing at locking granularity rather than raw contention volume.

## Mechanism

Under two-phase locking (2PL), a transaction acquires locks as it accesses rows and holds them until commit. When transaction A holds a lock transaction B needs, and B holds a lock A needs, neither can proceed — a cycle in the wait-for graph. The database periodically (or continuously) checks for such cycles and picks a victim, usually the transaction that would be cheapest to roll back or the one that entered the cycle last, and kills it with a deadlock error.

**Isolation level affects lock granularity beyond what's obvious.** Under MySQL InnoDB's default REPEATABLE READ, range queries and even some equality lookups on non-unique indexes take *gap locks* — locks on the space between index entries, not just the entries themselves — to prevent phantom rows from appearing mid-transaction. This means a query that looks like it touches one row can lock a range no other transaction realizes is contended, producing deadlocks between transactions that appear, from the application's view, to touch disjoint data.

**Long transactions are a multiplier, not just a slow path.** A transaction that holds locks while waiting on something outside the database — an HTTP call, a slow application computation — holds those locks for the duration of that external wait, not just for the database work. Every other transaction that needs an overlapping lock queues behind that entire external latency, turning a slow dependency elsewhere in the stack into a database-wide contention event.

**Lock escalation** (row locks promoted to table locks under memory pressure, in engines that support it) turns what was contained contention on a few rows into contention across the entire table, since escalation is a resource-management decision made independently of which specific rows are actually hot.

## Real-world sightings

**Percona Database Performance Blog, multiple posts on InnoDB gap locking under REPEATABLE READ.** Percona's engineering blog has repeatedly documented cases where applications hit deadlocks that don't correspond to any obvious overlapping row access, traced to gap locks taken by range-scanning `UPDATE` or `SELECT ... FOR UPDATE` statements under the default isolation level — a well-known enough class of bug that Percona and other MySQL consultancies maintain standing guidance to check gap locking before assuming application-level contention.

**Uber Engineering, "Why Uber Engineering Switched from Postgres to MySQL" (2016).** Uber's public post-mortem on their datastore migration cites, among other operational issues at their write volume, lock and vacuum-related contention behavior under Postgres's MVCC implementation as a factor in choosing a different storage engine — a concrete example of lock/contention characteristics becoming a first-order architectural decision at scale, independent of whether every detail of that specific post's reasoning aged well.

## Mitigations

### Consistent lock acquisition ordering

**What it is:** Whenever a transaction touches multiple rows or tables, always acquire locks in the same global order (e.g., always by ascending primary key) so that no two transactions can hold complementary locks in opposite order.

**Cost:** Requires discipline across every code path that ever locks more than one resource; there's no enforcement mechanism short of code review or a linter.

**How it backfires:** A new code path added later that violates the ordering reintroduces deadlocks that are invisible until it happens to run concurrently with a conflicting path under load — often long after the original ordering discipline was established and forgotten.

### No I/O inside a transaction

**What it is:** Gather everything needed from outside the database before opening the transaction, so the transaction's lock-holding duration is bounded by database work alone.

**Cost:** May require restructuring code that currently interleaves external calls with database writes for a reason (e.g., needing a value from an external service to decide what to write).

**How it backfires:** Splitting what was one logical, atomic operation into "gather, then transact" reopens a race window between the gather and the write that the original transaction's isolation was protecting against — trading a locking problem for a correctness problem.

### Lower isolation level

**What it is:** Move from REPEATABLE READ to READ COMMITTED to avoid gap locking on range scans, accepting non-repeatable reads within a transaction.

**Cost:** Weaker guarantees — a transaction can see different data on two reads of the same row, and phantom rows become possible.

**How it backfires:** Application code written assuming snapshot semantics (a consistent view for the whole transaction) doesn't error under the weaker isolation — it silently computes against data that shifted mid-transaction, a correctness bug with no error message to find it by. See [Write Skew and Read/Write Conflicts](write-skew-and-read-write-conflicts.md).

### Deadlock retry with backoff

**What it is:** Catch the deadlock error and retry the entire transaction from the start.

**Cost:** Requires the transaction to be safely retryable (idempotent, or free of side effects that shouldn't repeat), and adds latency to the affected request.

**How it backfires:** Under sustained contention, retries add load back onto the same contended rows, which can extend rather than resolve the pile-up — a database-scoped instance of [Retry Storms](../overload/retry-storms.md).

## Interactions

- [Optimistic Concurrency Control](optimistic-concurrency-control.md) — the alternative to locking up front: let transactions proceed and check for conflict only at commit.
- [Retry Storms](../overload/retry-storms.md) — deadlock retries under heavy contention are structurally the same amplification pattern.
- [Slow Is Worse Than Down](../dependencies/slow-is-worse-than-down.md) — a long transaction blocked on external I/O while holding locks is the database-side instance of a slow dependency consuming a shared resource.

## References

- Bernstein, P. and Newcomer, E. **Principles of Transaction Processing**, 2nd ed. Morgan Kaufmann, 2009.
  The standard reference on two-phase locking, deadlock detection, and victim selection.
- Percona Database Performance Blog. **Multiple posts on InnoDB locking and REPEATABLE READ.** https://www.percona.com/blog/
  Practical, production-derived documentation of gap locking behavior and its deadlock implications.
- Uber Engineering. **"Why Uber Engineering Switched from Postgres to MySQL."** *Uber Engineering Blog*, 2016.
  A public account of contention and operational characteristics factoring into a storage engine choice at scale.
