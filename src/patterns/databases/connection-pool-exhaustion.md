# Connection Pool Exhaustion

> **One-liner:** A database has a hard, global connection ceiling shared by every instance of every service that talks to it — scaling the app tier out doesn't add capacity, it slices the same ceiling into smaller pieces, and the failure shows up for free the first time autoscaling pushes past the point where instances × pool size stays under the limit.

## Symptom

- "Too many connections" / "FATAL: sorry, too many clients already" errors appear specifically after autoscaling the app tier up, not after a traffic spike per se.
- Adding app instances to handle more load makes database connection errors *worse*, even though each instance's own pool is sized identically to before.
- The database's connections-in-use metric sits pinned near `max_connections` while CPU and I/O on the database itself look unremarkable.
- Application-side "acquire connection from pool" calls time out even though the database is not saturated on any other resource.
- The problem reproduces reliably at a specific fleet size and disappears when the fleet is scaled back down, independent of request rate.

## Mechanism

Databases with a process-per-connection model (PostgreSQL) or thread-per-connection model (MySQL, historically) pay a real, fixed memory and scheduling cost per open connection — a few megabytes of RAM and a full OS process or thread, whether or not that connection is doing any work. This bounds the database to a `max_connections` setting that is deliberately conservative (Postgres defaults to 100), because the cost is paid per connection regardless of activity.

That ceiling is a **global** budget, not a per-client one. Each application instance opens its own connection pool, sized (correctly, in isolation) for that instance's expected concurrency. The total connections the database must support is `instance_count × pool_size_per_instance`. Nobody changes a single configuration value when the app tier autoscales — the app code, the pool size, and the database's `max_connections` are all untouched — yet crossing a certain instance count silently exceeds the ceiling, because the multiplication was never bounded by anything. The failure appears to come "from nowhere" precisely because none of the individually-reasonable settings changed; only their product did.

This is a different failure from the general connection-storm problem in [Connection Management](../load-balancing/connection-management.md): that page is about the *latency and thundering-herd cost* of establishing many connections at once to a stateless backend that can, in principle, accept unlimited connections. Here the problem is a **hard, low ceiling** on concurrently open connections to a stateful system, independent of how quickly or slowly those connections are established.

## Real-world sightings

**PgBouncer's own motivating documentation.** PgBouncer's README and project documentation explain its transaction-mode pooling explicitly as a workaround for Postgres's per-connection process cost: rather than each application connection holding a dedicated Postgres backend process for its entire lifetime, PgBouncer multiplexes many client connections onto a much smaller pool of actual Postgres connections, handing out a real connection only for the duration of a transaction. This is presented not as an optimization but as a necessity for any deployment where client connection count meaningfully exceeds what Postgres can hold open directly.

**Heroku Postgres connection limits guidance.** Heroku's Postgres documentation publishes explicit `max_connections` figures per plan tier and directly recommends PgBouncer for applications running multiple dynos (Heroku's unit of horizontal scaling), precisely because dyno count multiplied by per-dyno pool size is documented to exceed the database's connection limit well before the database itself is otherwise under load.

## Mitigations

### Connection pooler in front of the database

**What it is:** Insert PgBouncer, ProxySQL, or a managed equivalent (Amazon RDS Proxy) between the application fleet and the database, multiplexing many application-side connections onto a much smaller number of real database connections, typically in transaction mode.

**Cost:** Adds a network hop and an operational component; transaction-mode pooling breaks session-level features that depend on state persisting across statements on the same connection — advisory locks, session-level `SET` variables, prepared statement caches tied to a connection.

**How it backfires:** An application that silently relies on session state (a library that issues a session-scoped `SET` and assumes it holds for later statements) breaks in a way that doesn't error clearly — it just behaves as if the setting were never applied, because a later statement may land on a different underlying connection.

### Global connection budget accounting

**What it is:** Treat the database's `max_connections` as a budget explicitly divided among all known consumers (each service, each batch job), rather than letting each consumer size its own pool independently.

**Cost:** Requires central coordination — a shared config, or the pooler itself acting as the single source of truth for how much of the budget each consumer gets.

**How it backfires:** If a new consumer is added (a new service, an ad hoc analytics job) without recomputing and lowering everyone else's share, the newest consumer starves out existing ones exactly at the moment it's introduced — the failure mode this mitigation exists to prevent, just delayed to the next addition.

### Pool size scaled inversely to fleet size

**What it is:** Compute each instance's pool size as `budget / current_instance_count`, recomputed and redeployed whenever the fleet scales.

**Cost:** Requires this formula to be wired into the deployment or autoscaling pipeline and kept in sync as fleet size changes.

**How it backfires:** During a scaling event itself, old and new instance counts briefly disagree about the correct pool size, and the transition window can transiently exceed the budget even though the before-and-after states are each individually correct.

### Spread connections across read replicas

**What it is:** Route a portion of connections — read traffic specifically — to replicas, each of which carries its own separate `max_connections` ceiling, reducing the load on the primary's connection budget.

**Cost:** Reintroduces the staleness tradeoffs of [Read/Write Splitting](read-write-splitting.md) and [Replication Lag](replication-lag.md).

**How it backfires:** Doesn't help write-heavy workloads at all, since every write still competes for the primary's connection budget regardless of how many replicas exist.

## Interactions

- [Connection Management](../load-balancing/connection-management.md) — the general connection-storm and pool-sizing problem for stateless backends; this page is the special case where the backend is a stateful database with a hard, small, shared ceiling instead of an arbitrarily scalable one.
- [Read/Write Splitting](read-write-splitting.md) — spreading connections across replicas is a mitigation here, but it inherits that pattern's staleness tradeoffs.
- [Static Stability](../capacity/static-stability.md) — sizing pools for the fleet's peak size rather than its current size is the same discipline static stability asks for elsewhere.

## References

- PgBouncer Documentation. **"Why Use PgBouncer?"** https://www.pgbouncer.org/
  Explains the per-connection process cost in PostgreSQL and the transaction-mode multiplexing design that works around it.
- Heroku Dev Center. **"Postgres Concurrency and Connection Pooling."** https://devcenter.heroku.com/
  Documents connection limits per plan tier and the recommendation to use PgBouncer once dyno count multiplies past the limit.
- Kleppmann, M. **Designing Data-Intensive Applications.** O'Reilly, 2017.
  Chapter 6 discusses resource partitioning and shared-limit contention in distributed systems generally.
