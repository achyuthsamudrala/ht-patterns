# Hot Keys

> **One-liner:** A single cache key requested at 100,000 RPS saturates one cache node regardless of cluster size — traffic concentration violates the assumption of uniform distribution that horizontal scaling depends on.

## Symptom

- One cache node's CPU or network bandwidth saturated while other nodes are idle.
- Latency percentiles spike for requests touching a small set of keys while all others are served normally.
- Autoscaling adds nodes but doesn't help — new nodes don't receive traffic for the hot key.
- Cache client's per-node connection pool exhausted for one node; healthy for all others.
- Key-level metrics (if available) show one key receiving orders of magnitude more traffic than the median.

## Mechanism

Most distributed caches (Memcached, Redis Cluster, Dynamo) distribute keys across nodes using a hash function: `node = hash(key) % num_nodes` (or consistent hashing). The distribution is designed to spread load uniformly across the cluster.

The hot key problem violates this assumption: the distribution is uniform in key space, but not in request frequency space. A key accessed 10,000 times more frequently than average sends 10,000× the requests to a single node. Cluster size does not help — adding more nodes doesn't redistribute the hot key's traffic; the key's hash determines its node, and that mapping is fixed.

**Sources of hot keys:**
- Viral content (a tweet, video, or post that suddenly gets large attention).
- Shared configuration or feature flags loaded by every request (e.g., `global_feature_flags`).
- User session data for a single extremely active account.
- Small enumerations with high access rate (e.g., `country_list`, `currency_rates`).

**Network saturation vs. CPU saturation:** A hot key on a small value saturates the cache node's CPU (many small requests). A hot key on a large value saturates the cache node's network egress (repeated large payload transmission). Both cap out the node independently of cluster size.

**The replica illusion:** Redis Cluster allows replicas for read scaling. This helps uniform workloads but is often insufficient for hot keys: if the hot key receives 100,000 reads/second and each replica handles 10,000 reads/second, you need 10 replicas for that one key. Redis Cluster doesn't support per-key replica scaling.

**Distinguishing hot key from shard imbalance:** Shard imbalance means many keys hashed to the same node (poor hash function). Hot keys mean one key receiving extreme traffic. Shard imbalance shows many keys elevated on one node; hot key shows one key dominating.

## Real-world sightings

**Nishtala et al., "Scaling Memcache at Facebook" (NSDI 2013).** The paper discusses "hot spots" as a known problem in Memcache deployments at Facebook. For extremely popular items (profiles of celebrities, viral content), a single Memcache server could be overwhelmed. Facebook's mitigation included local in-process caches on web servers and "regional pools" that distribute replicas of hot keys.

**Redis Labs / Redis Enterprise documentation.** The Redis Enterprise documentation explicitly discusses hot key detection and recommends local client-side caches as the primary mitigation for keys that exceed single-node throughput. The docs note that read replicas are a partial solution but have inherent limits.

## Mitigations

### Local in-process cache (L1 cache)

**What it is:** Maintain a small, short-TTL in-process cache (in the application's own memory) for the hottest keys. Requests served by L1 never reach the cache cluster. The cluster's node sees only misses that fall through L1.

**Cost:** Adds memory pressure on the application host. Short TTL means the application serves slightly stale data. L1 cache is not shared across requests on different threads without synchronization.

**How it backfires:** Under large deployments (1000 app hosts), even a brief L1 TTL causes each host to independently miss at L1 expiry, generating N=1000 simultaneous misses to the cache cluster per hot key per TTL cycle. Combine with [Stampede and Coalescing](stampede-and-coalescing.md) mitigations.

### Key sharding (virtual key distribution)

**What it is:** Store N copies of the hot key's value under different key names: `hot_key#0`, `hot_key#1`, ..., `hot_key#(N-1)`. On each request, randomly pick a shard: `shard = random(0, N)`. Reads distribute across N cache nodes. Writes update all N copies.

**Cost:** N-way write amplification on every update. Consistency: all N shards should be updated atomically, which is complex without transactions. Short TTL on each shard limits inconsistency window.

**How it backfires:** If writes are slow or fail partway, some shards hold the old value and some hold the new, causing inconsistent results. Suitable only for data that tolerates brief inconsistency.

### Dedicated node or pool for hot keys

**What it is:** Identify hot keys (via access-frequency monitoring) and route them to a dedicated set of cache nodes not in the regular hash ring. Hot-key traffic is isolated so normal-traffic nodes are not affected.

**Cost:** Requires dynamic hot key detection and routing table updates. Adds an extra lookup step per request.

**How it backfires:** Hot key sets change over time (yesterday's viral post is today's archive). A hot key that is no longer hot continues consuming dedicated resources if the hot list isn't pruned.

## Interactions

- [Stampede and Coalescing](stampede-and-coalescing.md) — a hot key expires or is invalidated → stampede. High request rate + expiry event = large stampede.
- [Consistent Hashing](../load-balancing/consistent-hashing.md) — consistent hashing solves rehash churn but not hot key concentration.
- [Cache as Hard Dependency](cache-as-hard-dependency.md) — the hot node is a single point of failure; if it goes down, all requests for the hot key miss simultaneously.

## References

- Nishtala, R. et al. "Scaling Memcache at Facebook." *NSDI 2013*.
  Section 3.4 discusses hot spots and Facebook's multi-tier mitigation approach.
- Redis documentation. "Redis Cluster Specification."
  Section on data sharding explains hash slots and why per-key sharding doesn't address hot keys at the cluster level.
- Amazon Web Services. "Amazon ElastiCache Best Practices."
  The "Addressing Hot Partitions" section covers detection and mitigation of hot keys in ElastiCache deployments.
