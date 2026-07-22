# Databases

Database patterns address how services interact with a stateful, hard-to-scale
dependency. The defining difference from a stateless dependency: reads and writes
to the same data must eventually agree with each other, not just complete quickly.
Every mitigation in this section is really a decision about which consistency
guarantee to give up, and when.

## Patterns in this section

- [Replication Lag](replication-lag.md)
- [Read/Write Splitting](read-write-splitting.md)
- [Lock Contention and Deadlocks](lock-contention-and-deadlocks.md)
- [Optimistic Concurrency Control](optimistic-concurrency-control.md)
- [Write Skew and Read/Write Conflicts](write-skew-and-read-write-conflicts.md)
- [Connection Pool Exhaustion](connection-pool-exhaustion.md)
- [Hot Partitions and Sequential Keys](hot-partitions-and-sequential-keys.md)
- [Failover and Split-Brain](failover-and-split-brain.md)
