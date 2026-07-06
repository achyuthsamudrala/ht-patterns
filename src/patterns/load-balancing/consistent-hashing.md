# Consistent Hashing

> **One-liner:** Consistent hashing achieves locality (same key → same backend) with minimal redistribution on membership changes — but naive implementations create hot spots, and bounded-load variants trade locality for balance.

## Symptom

*Without consistent hashing (using modular hashing):*
- After any node add/remove, cache hit rate drops to near zero — all keys remapped to new nodes.
- Warmup required after every scaling event; latency spikes during warmup.

*With consistent hashing, hot spots:*
- Some nodes receive disproportionate traffic (hot keys on popular ring positions).
- Load is uneven across nodes even when key access is uniform — uneven ring position assignment.
- Node removal causes one neighboring node to absorb all the removed node's traffic, creating a temporary hot node.

*With consistent hashing, correct operation:*
- Node add/remove redistributes ~1/N of keys; other keys remain on the same node.
- Cache hit rate stays high through cluster membership changes.

## Mechanism

**The modular hashing problem:** In modular hashing, `node = hash(key) % N`. When N changes (a node is added or removed), nearly every key maps to a new node. All per-node state (cache, connection affinity) is invalidated simultaneously.

**Consistent hashing:** Map both keys and nodes to positions on a hash ring (a circle of [0, 2^32) positions). Each key routes to the node responsible for the arc immediately clockwise from the key's position. When a node is added, it takes responsibility for the arc between itself and its predecessor — affecting only the keys in that arc (~1/N). When a node is removed, its arc is absorbed by its successor — again, only ~1/N of keys are affected.

**The virtual node problem:** If nodes are assigned a single ring position each, the distribution across nodes is highly uneven (some positions are clustered, leaving some nodes with large arcs and others with small ones). At N=10 nodes, the standard deviation of load is approximately 30% of the mean with a single position per node.

Solution: assign each physical node V virtual positions on the ring. With V=150, standard deviation falls to ~2% of mean. The tradeoff: larger V means more ring state and more expensive membership updates (O(V log N) operations per change).

**Bounded-load consistent hashing:** Extends consistent hashing with a load check. When the primary node (clockwise neighbor) is "overloaded" (serving more than (1+ε) times the average requests), the key is instead routed to the next clockwise node. This prevents any node from exceeding average load by more than (1+ε), at the cost of key locality:

- At (1+ε) load factor: strict locality maintained until the node is at (1+ε)× average.
- Above (1+ε): the key falls back to the next ring neighbor.

Fallback breaks the key-locality guarantee that consistent hashing provides. Cache hit rate drops for the over-budget node's keys.

**When locality is required vs. optional:**

- *Cache routing:* Locality is strongly preferred (same key → same node → cache hit). Use standard consistent hashing; tolerate the hot-spot risk from hot keys by adding [Hot Key](../caching/hot-keys.md) mitigations.
- *Stateless RPC routing:* Locality is not required. Use P2C least-outstanding (see [Algorithms Under Stress](algorithms-under-stress.md)) for better load distribution.
- *Inference KV cache:* Locality is required for prefix cache reuse. Use cache-aware routing with consistent hashing; combine with bounded-load for overloaded nodes.

## Real-world sightings

**Karger, D. et al., "Consistent Hashing and Random Trees" (STOC 1997).** The original paper introducing consistent hashing in the context of distributed web caching. The paper proves the O(1/N) redistribution property and proposes virtual nodes for even distribution.

**Nishtala et al., "Scaling Memcache at Facebook" (NSDI 2013).** Facebook uses consistent hashing for Memcache key distribution. The paper describes the need for virtual nodes to achieve even distribution and notes that consistent hashing was necessary because modular hashing's full redistribution on cluster membership changes was operationally unacceptable at scale.

**Mirrokni, V. et al., "Consistent Hashing with Bounded Loads" (SODA 2018).** The bounded-load extension, developed at Google. The paper proves that bounded-load consistent hashing achieves (1+ε) load factor with O(log N / ε) virtual nodes per physical node, compared to O(log N / ε²) without bounded load.

## Mitigations

### Virtual nodes for even load distribution

**What it is:** Assign each physical node V virtual positions on the ring. Each virtual position is a hash of (node_id, replica_index). The ring is populated with V×N virtual positions; each key routes to the nearest clockwise virtual position, then maps to the owning physical node.

**Cost:** Ring state is O(V×N); membership updates are O(V×log(V×N)).

**How it backfires:** High V reduces load variance but increases the cost of ring operations. Hot keys — a single key accessed at extreme frequency — are not helped by virtual nodes (one key always maps to one position).

### Bounded-load routing for overloaded nodes

**What it is:** Track per-node request rate. When the primary node exceeds (1+ε)× average load, route to the next clockwise node instead.

**Cost:** Requires per-node load tracking; breaks key locality for overloaded keys.

**How it backfires:** If load is uniformly high (all nodes overloaded), fallback cascades through the ring. The bounded-load constraint becomes equivalent to round-robin.

### Rendezvous hashing (highest random weight)

**What it is:** An alternative to ring-based consistent hashing. For each key, compute a hash of (key, node_id) for every node; route to the node with the highest hash. On node addition/removal, only the affected subset of keys redistributes. No ring state required.

**Cost:** O(N) hash computations per routing decision (vs. O(log N) ring lookup). Unsuitable for large N without optimizations.

**How it backfires:** At large N (hundreds of nodes), per-request computation cost is significant. Caching the routing decision per key is common.

## Interactions

- [Hot Keys](../caching/hot-keys.md) — consistent hashing routes hot keys deterministically to one node; the hot key pattern requires additional mitigation on top of consistent hashing.
- [Algorithms Under Stress](algorithms-under-stress.md) — for stateless routing, P2C is generally superior; consistent hashing is specifically for stateful locality.
- [Inference KV Cache](../inference/kv-cache-pressure.md) and [Prefix Caching](../inference/prefix-caching.md) — inference serving uses consistent hashing for KV cache and prefix cache affinity.

## References

- Karger, D. et al. "Consistent Hashing and Random Trees: Distributed Caching Protocols for Relieving Hot Spots on the World Wide Web." *STOC 1997*.
  Original paper; foundational reference for ring-based consistent hashing.
- Mirrokni, V. et al. "Consistent Hashing with Bounded Loads." *SODA 2018*.
  The bounded-load extension; describes the (1+ε) load factor guarantee.
- Nishtala, R. et al. "Scaling Memcache at Facebook." *NSDI 2013*.
  Section 4 describes Memcache cluster architecture with consistent hashing and virtual nodes.
