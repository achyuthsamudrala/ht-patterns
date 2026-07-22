# Hot Partitions and Sequential Keys

> **One-liner:** A sharded database only scales if writes spread evenly across shards; a monotonically increasing key — an auto-increment ID, a time-ordered UUID — sends every new write to whichever shard holds the newest key range, turning an N-shard cluster into a 1-shard bottleneck with N−1 idle bystanders.

## Symptom

- One shard or partition shows an order of magnitude more write throughput than its siblings, which sit comparatively idle.
- Aggregate write throughput plateaus at roughly what a single shard can do, regardless of how many shards exist.
- The hot shard is consistently the one holding the most recently created key range.
- Adding more shards to the cluster doesn't increase throughput — the new shards simply never receive traffic, because new keys never sort into their range.
- CPU or I/O graphs show one clearly saturated node in an otherwise balanced, low-utilization cluster.

## Mechanism

Range-based partitioning assigns each shard a contiguous range of the key space. If the partition key is monotonically increasing — an auto-increment primary key, a time-ordered UUID (UUIDv1), a timestamp-prefixed identifier — every newly inserted row has a key greater than every existing row, so every new write sorts into the range currently owned by exactly one shard: the one holding the tail end of the key space. The other shards, holding older, closed ranges, receive no new writes at all. The cluster's total write capacity for new data is capped at what that one shard can do, no matter how many shards exist.

Hash-based partitioning avoids this specific failure for uniformly random keys, since a good hash function scatters sequential input across the full range of output. But it reintroduces the same class of problem for any partition key whose *value distribution* is skewed rather than its raw bit pattern — a `tenant_id` partition key where one large tenant generates most of the traffic hashes to one shard just as reliably as a sequential ID does, because the skew lives in which values occur, not in whether the hash function is uniform.

Systems with per-partition throughput allocation (rather than sharing capacity across all partitions of a table) make this worse: even if the underlying storage has spare aggregate capacity, a single overloaded partition is throttled at its own fixed allocation while the rest of the cluster's capacity goes unused, unless the system dynamically reallocates capacity to follow the hot spot.

## Real-world sightings

**Instagram Engineering, "Sharding & IDs at Instagram" (2012).** Instagram's public engineering post describes designing a custom 64-bit ID generation scheme specifically to avoid the sequential-key hotspotting problem: rather than a simple auto-increment ID (which would concentrate all new rows on one shard) or a fully random ID (which would break time-ordering and make range queries impossible), their scheme encodes a timestamp, a logical shard ID, and an auto-increment sequence into each ID, distributing new writes across shards by design while preserving rough time-sortability.

**Amazon DynamoDB, adaptive capacity.** AWS's DynamoDB documentation describes "adaptive capacity" as a feature introduced specifically because early partition-level throughput allocation meant a single popular partition key (a hot item, or a skewed access pattern across a partition's key range) could be throttled even while the table's overall provisioned capacity sat unused elsewhere. AWS's own partition-key design guidance explicitly warns against monotonically increasing keys — e.g., a timestamp as a leading key component — for exactly this reason.

## Mitigations

### Hashed or shuffled partition key

**What it is:** Hash the natural key (or reverse/shuffle its bits) before using it to select a partition, so sequential input no longer produces sequential shard assignment.

**Cost:** Range scans across the natural key order — pagination by ID, time-range queries — become expensive or impossible, since consecutive logical keys are now scattered across every shard.

**How it backfires:** Any downstream code that relied on natural key ordering (cursor-based pagination, "give me the last 100 rows") must now scatter-gather across all shards and re-sort, or maintain a separate secondary index just to recover the ordering the hash discarded.

### Composite or salted keys

**What it is:** Prepend a random or rotating salt (one of *N* buckets) to a logical key, spreading writes to what was one hot key across *N* physical rows.

**Cost:** Reads must fan out across all *N* salt buckets and reassemble the logical entity, adding read-side complexity and cost.

**How it backfires:** Too few buckets and the hotspot simply moves to a handful of still-hot buckets instead of disappearing; too many and the read-side fanout cost dominates for an entity that's read far more often than written.

### ID scheme that encodes shard assignment directly

**What it is:** Generate IDs that embed a target shard chosen by an explicit policy (round-robin, or a lighter-weight rule than "always the newest"), as in Instagram's ID scheme — rather than letting a database's own auto-increment or clock-based default decide.

**Cost:** Requires a custom ID generation service or library in place of a database default, and coordination on the encoding scheme across every writer.

**How it backfires:** The shard-selection policy embedded in the scheme can itself be uneven — simple round-robin is fine, but any policy that tries to pick "the least loaded shard" needs live load feedback that can be stale by the time an ID is actually used.

### Per-partition monitoring with automatic rebalancing

**What it is:** Monitor per-partition load and automatically reallocate capacity or split a hot partition, as DynamoDB's adaptive capacity does, or perform online shard splitting.

**Cost:** Operational complexity of running a rebalancing system, plus the rebalancing operation's own resource cost.

**How it backfires:** Rebalancing a partition requires reading and redistributing its data, which consumes I/O and network bandwidth on the very partition that's already hottest — the fix can transiently make the hot partition's user-facing latency worse before the rebalance completes and relieves it.

## Interactions

- [Hot Keys](../caching/hot-keys.md) — the cache-layer expression of the identical key-popularity skew problem.
- [Shuffle Sharding](../multitenancy/shuffle-sharding.md) — limits blast radius across tenants but doesn't address write-throughput skew from a single hot key within a shard.
- [Optimistic Concurrency Control](optimistic-concurrency-control.md) — a hot partition receiving concurrent writes to the same logical entity compounds with OCC's retry costs on that entity.

## References

- Instagram Engineering. **"Sharding & IDs at Instagram."** *Instagram Engineering Blog*, 2012.
  Describes the 64-bit timestamp/shard/sequence ID scheme designed to avoid sequential-key hotspotting while preserving time-sortability.
- Amazon Web Services. **"Choosing the Right DynamoDB Partition Key"** and **"Adaptive Capacity."** *AWS Documentation*.
  Explains per-partition throughput allocation, the hot-partition problem it creates, and the adaptive capacity feature built to address it.
- DeCandia, G. et al. **"Dynamo: Amazon's Highly Available Key-value Store."** *SOSP 2007*.
  Foundational paper on consistent hashing for partition assignment and the load-balancing tradeoffs of different hashing schemes.
