# Replication Lag

> **One-liner:** Replicas apply writes asynchronously behind the primary; a client that reads from a replica before its own write lands sees the write vanish — the exact bug that's hardest to reproduce because it depends on which replica you happened to hit.

## Symptom

- A user submits data, the confirmation page reloads, and the data is gone — then reappears seconds later on a refresh.
- Replica lag metrics (`seconds_behind_master` in MySQL, `replay_lag` from `pg_stat_replication` in Postgres) climb during write bursts and recover afterward.
- Lag is proportional to primary write throughput, not to replica read load — the replica can be otherwise idle and still lag.
- "Read-your-writes" bug reports cluster around flows that read immediately after a write (redirect-after-post, submit-then-list).
- Different replicas show different lag at the same instant; the same user sees inconsistent results across two requests routed to two different replicas.

## Mechanism

Asynchronous replication ships a log of committed changes from the primary to each replica — the write-ahead log (WAL) in Postgres streaming replication, the binary log (binlog) in MySQL. The replica applies this log in order. Two things bound how fast a replica can catch up:

1. **Network transfer time** for the log stream, usually small relative to (2).
2. **Apply throughput on the replica.** Historically, replay was single-threaded per replication stream, so a replica with slower disks or CPU than the primary — or one simply doing other work, like serving reads — falls behind under sustained write load no matter how fast the network is. Modern engines (MySQL multi-threaded replication, Postgres logical replication) parallelize apply across independent transactions, but a workload with cross-table dependencies still serializes.

Lag is not constant: it grows during write bursts (batch jobs, backfills, traffic spikes) and drains during quiet periods. A replica pool with independently varying lag per node means "eventual consistency" isn't a single number — it's a different number per replica, per moment, and a client has no way to know which replica it landed on without asking.

**Why read-your-writes breaks specifically:** a write commits on the primary and returns success to the client. The client's next read is load-balanced to some replica, chosen without regard to whether that replica has applied the write yet. If the write is still in flight down the replication log, the read returns the pre-write state. The bug is invisible in testing because a single-threaded test process almost always reads from the same replica session-consistently, or the lag at test-time load is near zero.

## Real-world sightings

**Nishtala et al., "Scaling Memcache at Facebook" (NSDI 2013).** Facebook's cross-region cache architecture explicitly confronts replica lag: their MySQL replicas in remote regions lag behind the primary region by seconds, and a naive cache-fill from a lagging replica would cache stale data durably (since the cache doesn't re-check). Their fix — "remote markers" that flag recently-written keys so a subsequent read in the remote region routes to the primary region instead of the local lagging replica — is a direct, production-scale instance of the read-your-writes mitigation below.

**Amazon Aurora (Verbitski et al., SIGMOD 2017).** Aurora's quorum-based storage layer was designed partly to reduce the replica lag problem: because storage nodes replicate below the database engine rather than via logical log shipping to full replica engines, typical Aurora replica lag is sub-10ms rather than the seconds-scale lag common in traditional MySQL/Postgres replication. The paper frames this explicitly as reducing the operational cost of the read-scaling pattern.

## Mitigations

### Read-your-writes stickiness

**What it is:** After a client writes, route that client's subsequent reads to the primary (or to the specific replica known to have applied the write) for a short window, instead of to the general replica pool.

**Cost:** Reduces read scaling for exactly the clients who just wrote — often the most active ones — and adds load back onto the primary.

**How it backfires:** During a write-heavy period, a large fraction of clients are "recently written" and stick to the primary simultaneously, which can push read load back onto the primary at the worst possible time — right when it's already busiest with writes.

### Lag-aware replica routing

**What it is:** Health-check each replica's lag and evict any replica beyond a threshold from the read pool, similar to Vitess's tablet health checks that mark a replica unhealthy when replication delay exceeds a configured bound.

**Cost:** Shrinks the effective replica pool whenever lag rises, reducing available read capacity exactly when write load (the cause of lag) is high.

**How it backfires:** If a primary write burst causes every replica to lag past the threshold simultaneously, the entire replica pool is evicted at once and all reads fail over to the primary — a cascading overload triggered by the very mitigation meant to prevent stale reads.

### Causal read tokens (position-aware reads)

**What it is:** The client remembers the log position (LSN, GTID) of its last write and a subsequent read waits until the chosen replica's applied position is at least that recent (Postgres `pg_wal_lsn_diff` polling, MySQL `WAIT_FOR_EXECUTED_GTID_SET`).

**Cost:** Adds latency to the read (bounded wait for catch-up) and requires the client or an intermediary to track and pass positions.

**How it backfires:** If the replica is falling behind under sustained load rather than catching up, the wait either blocks until a timeout (converting a stale read into a slow one) or must be capped, at which point the guarantee silently degrades back to "maybe stale."

### Semi-synchronous replication

**What it is:** The primary waits for acknowledgment from at least one replica before considering a write committed, bounding the worst-case lag on that replica to near-zero.

**Cost:** Adds commit latency to every write, proportional to the round trip to the acknowledging replica.

**How it backfires:** If the acknowledging replica itself slows down, it throttles every write on the primary — the durability guarantee for reads is bought by making the primary's availability depend on a specific replica's health.

## Interactions

- [Read/Write Splitting](read-write-splitting.md) — replication lag is precisely the risk that makes routing reads to replicas a per-query decision rather than a free scaling lever.
- [Cache as Hard Dependency](../caching/cache-as-hard-dependency.md) — the read-your-writes problem here is structurally the same one caching layers have with stale reads after a write.
- [Failover and Split-Brain](failover-and-split-brain.md) — a lagging replica promoted during a failure loses exactly the unreplicated tail of writes that hadn't reached it yet.

## References

- Nishtala, R. et al. **"Scaling Memcache at Facebook."** *NSDI 2013*.
  Introduces remote markers for read-your-writes consistency across regions with lagging replicas.
- Verbitski, A. et al. **"Amazon Aurora: Design Considerations for High Throughput Cloud-Native Relational Databases."** *SIGMOD 2017*.
  Describes a storage architecture that reduces typical replica lag to single-digit milliseconds.
- Kleppmann, M. **Designing Data-Intensive Applications.** O'Reilly, 2017.
  Chapter 5 covers replication lag, read-your-writes, monotonic reads, and consistent prefix reads as named, distinct guarantees.
