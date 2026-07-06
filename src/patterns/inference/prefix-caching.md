# Prefix Caching

> **One-liner:** Routing requests with matching prompt prefixes to the same GPU host reuses KV cache and eliminates redundant prefill — but routes all traffic sharing a popular system prompt to one host, creating a hot-spot that defeats load balancing.

## Symptom

- Prefix-aware routing enabled; one host significantly busier than all others.
- Cache hit rate high globally; TTFT low for most requests; one host at 100% KV capacity.
- A popular system prompt (shared by a RAG pipeline, an assistant persona, or a high-traffic tenant) concentrating all its traffic on a single backend.
- Removing prefix-aware routing immediately balances load but raises TTFT (more prefill re-computation).

## Mechanism

**What prefix caching saves:**

For requests that share a prompt prefix (a system prompt, a document in a RAG query, a conversation history up to a branching point), the KV cache for the shared portion is identical across requests. If a GPU host already has the KV cache for the prefix from a prior request, it can skip prefill for those tokens entirely — they are already in HBM.

Prefill time is roughly proportional to prompt length and is compute-bound (all prompt tokens processed in parallel). A 2,000-token system prompt at 0.1ms/token costs 200ms of prefill. If prefix caching achieves a 90% hit rate, effective TTFT falls from 200ms+ to ~20ms for cache-hitting requests.

**Prefix-aware routing mechanics:**

To reuse cached prefixes, the router must send matching-prefix requests to the host that has the prefix cached. This is implemented by hashing the prefix (or the first N tokens) and routing to a consistent set of hosts, analogous to consistent hashing by cache key.

SGLang's RadixAttention (Zheng et al., 2024) extends this: it stores prefix KV caches in a radix tree (prefix trie), allowing partial reuse of any shared prefix, not just exact matches. Requests are routed based on their longest matching prefix node in the tree.

**The hot-spot problem:**

If a prefix is shared by a large fraction of traffic (e.g., a widely-used system prompt), prefix-aware routing sends all traffic matching that prefix to the same host. The host receives:
- The full compute load for that prefix's share of traffic.
- KV memory pressure from accumulating all those requests' KV caches.

This is the inference analogue of the consistent-hashing hot-key problem. See [Hot Keys](../caching/hot-keys.md) and [Consistent Hashing](../load-balancing/consistent-hashing.md).

**The hit rate vs. load balance tradeoff:**

The tension is direct:
- *Maximum hit rate*: route all requests with the same prefix to exactly one host → perfect KV reuse, but O(1/N) concentration of traffic on a single host.
- *Maximum load balance*: route requests randomly → zero KV reuse (every request pays full prefill cost), but perfectly even load distribution.

Neither extreme is correct; the optimum depends on how expensive prefill is relative to the cost of imbalanced load.

## Real-world sightings

**SGLang RadixAttention (Zheng et al., 2024).** SGLang implements RadixAttention to efficiently cache and reuse prefix KV caches. The paper reports 1.1–2.5× throughput improvement for workloads with shared prefixes (RAG, few-shot prompting, long documents). The system uses a radix tree for prefix matching and routes based on longest matching prefix.

**vLLM automatic prefix caching.** vLLM added automatic prefix caching (APC) in v0.4.0, implementing hash-based prefix identification and reuse. The vLLM documentation explicitly warns that APC works best when the top-K most popular prefixes are identified and can be replicated — echoing the hot-spot concern.

## Mitigations

### Prefix replication across multiple hosts

**What it is:** For the K most popular prefixes (measurable by routing frequency), pre-compute and replicate their KV cache across multiple hosts. Requests matching these popular prefixes are routed to any of the replica hosts rather than a single host. Replication can be done by re-running prefill on each replica or by copying KV pages via host-to-host transfer (NVLink or InfiniBand).

**Cost:** Each additional replica for a popular prefix consumes KV memory on that host. A 2,000-token system prompt at 524 KB/1000 tokens uses ~1 GB of KV per host.

**How it backfires:** Replication must be invalidated when the prefix changes (e.g., a new system prompt version). Transfer-based replication requires inter-host bandwidth; recompute-based replication wastes compute.

### Hybrid routing: prefix-aware with load-aware fallback

**What it is:** Route to the host with the matching prefix *if* that host's load (KV occupancy, queue depth) is below a threshold. If the preferred host is overloaded, fall back to the least-loaded host that has a partial prefix match, or to random load-balanced routing if no match exists.

**Cost:** Cache miss on fallback routes → full prefill cost. The fallback rate is the cost of load balancing correctness.

**How it backfires:** If the preferred host is *always* overloaded (traffic exceeds single-host capacity), the fallback fires constantly, eliminating the caching benefit entirely. Replication is required to break the throughput ceiling.

### Prefix popularity tracking with dynamic routing weights

**What it is:** Monitor prefix usage frequency continuously. For high-frequency prefixes: route with hash-pinning (consistent assignment). For low-frequency prefixes: route randomly (load balance dominates). The threshold between "frequent enough to pin" and "rare enough to randomize" is tuned to balance hit rate against load imbalance.

**Cost:** Requires online prefix frequency tracking and dynamic routing table updates.

**How it backfires:** Prefix popularity can shift suddenly (a new tenant starts using a new system prompt, or a viral prompt becomes dominant). Routing table updates must propagate quickly; stale routing during transitions causes either hot-spots (old popular prefix still pinned) or cache misses (new popular prefix not yet pinned).

## Interactions

- [Hot Keys](../caching/hot-keys.md) — the same hot-spot mechanics as key-sharding hot keys; prefix caching in inference and key caching in distributed caches face identical load concentration problems.
- [Consistent Hashing](../load-balancing/consistent-hashing.md) — prefix routing is implemented as consistent hashing on prefix hash; the bounded-load variant directly applies to limit hot-spot severity.
- [KV Cache Pressure](kv-cache-pressure.md) — popular-prefix replication consumes KV memory that competes with active sequence KV cache.
- [Mixed Request Patterns](../multitenancy/mixed-request-patterns.md) — requests for popular vs. rare prefixes have different TTFT profiles; mixing them in one batch complicates SLO management.

## References

- Zheng, L. et al. "SGLang: Efficient Execution of Structured Language Model Programs." *arXiv 2312.07104*, 2024.
  Introduces RadixAttention for prefix-aware KV reuse; describes the routing algorithm and throughput gains.
- Kwon, W. et al. "Efficient Memory Management for Large Language Model Serving with PagedAttention." *SOSP 2023*.
  Describes prefix sharing in the PagedAttention memory model; copy-on-write for forked sequences is the mechanism underlying prefix replication.
