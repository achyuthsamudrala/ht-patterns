# Shuffle Sharding

> **One-liner:** Assigning each tenant a random K-of-N shard subset limits blast radius to (K/N)^K — a noisy neighbor who crashes their 2-of-10 shards has a 4% chance of sharing even one shard with another tenant.

## Symptom

*Shuffle sharding is a design pattern, not a failure mode. Symptoms indicating its absence:*

- A single misbehaving tenant degrades or crashes capacity that affects other tenants.
- Failure in a region serving one customer's traffic propagates to other customers sharing the same infrastructure.
- "Noisy neighbor" events: one tenant's load spike causes degradation visible to unrelated tenants.
- Post-incident analysis reveals that all affected tenants shared common infrastructure (same shards, same AZ, same host).

## Mechanism

**Simple sharding: O(1/N) blast radius:**

If you have N shards and route all of tenant T's traffic to shard i, a failure in shard i affects every tenant on shard i — approximately 1/N of tenants share that shard. This is simple consistent hashing.

**The birthday paradox problem:** With simple random assignment (each tenant assigned exactly 1 shard), two tenants share a shard with probability 1/N. For N=100, 1%. Seems fine — but with 10,000 tenants, expected number of tenant pairs sharing a shard is enormous.

**Shuffle sharding blast radius:**

Shuffle sharding assigns each tenant K of N shards instead of exactly 1. All of the tenant's traffic is distributed across their personal K-shard pool. Requests from tenant T only reach shards in T's assigned subset.

The probability that any two tenants share at least one shard:

```
P(share ≥ 1 shard) = 1 - C(N-K, K) / C(N, K)
≈ 1 - (1 - K/N)^K     (approximation)
= (K/N)^K              (blast radius fraction)
```

For K=2, N=10: blast radius = (2/10)^2 = 4%.
For K=3, N=100: blast radius = (3/100)^3 = 0.027%.
For K=4, N=1000: blast radius = (4/1000)^4 = 2.56 × 10^-11 (essentially zero).

The key insight: by increasing K and N together, you can reduce blast radius exponentially while keeping the per-tenant shard count constant (K remains the replication factor the tenant actually uses). The cost is N shards instead of 1.

**Implementation:**

Tenant-to-shard assignment is computed from a stable hash of the tenant ID:
```python
import hashlib, random

def tenant_shards(tenant_id, K, N):
    """Assign K shards from N to tenant_id deterministically."""
    shards = list(range(N))
    h = int(hashlib.sha256(tenant_id.encode()).hexdigest(), 16)
    rng = random.Random(h)
    rng.shuffle(shards)
    return shards[:K]
```

This assignment is stable (same tenant always gets same shards) and evenly distributed across the fleet.

**When isolation breaks down:** Shuffle sharding limits the blast radius of correlated failures — a tenant who generates anomalous load that crashes their assigned shards only crashes K shards. But it does not protect against:
- Global configuration changes that affect all shards.
- Network-level failures affecting the whole fleet.
- Resource exhaustion that propagates across shard boundaries (e.g., a database shared by all shards).

Shuffle sharding is one layer of isolation, not complete isolation.

## Real-world sightings

**Amazon Web Services "Shuffle Sharding: Massive and Magical Fault Isolation" (Colm MacCárthaigh, AWS re:Invent 2014).** The concept was introduced publicly by AWS's Colm MacCárthaigh to describe how AWS Route 53 and other services isolate customer traffic. The talk describes the blast radius formula and gives examples of K and N values used in production. The AWS Builders' Library subsequently published an essay on the topic.

**Amazon Route 53.** Route 53 uses shuffle sharding internally to ensure that a DNS attack against one customer's zone does not affect other customers. Each zone is assigned a subset of Route 53's servers; a flood targeting one zone only affects servers in that subset. Other zones on those servers may be affected, but the blast radius is (K/N)^K.

## Mitigations

### Tenant-specific shard assignment

**What it is:** Precompute and store each tenant's K-shard assignment at tenant onboarding. Route all requests from that tenant to their assigned shards using the routing layer. Assignment is stable unless explicitly rotated.

**Cost:** Requires storing and distributing tenant → shard mapping to the routing layer. K×N more total resources than assigning one shard per tenant (though typically K is small: 2–5).

**How it backfires:** If shard assignments are not stored durably, a restart of the routing component recalculates assignments. If the hash seed changes, tenants are remapped to different shards (losing any tenant-specific state cached on the original shards).

### Shard assignment rotation after incidents

**What it is:** After a tenant is associated with an incident (they were isolated in a blast or they caused one), rotate their shard assignment to a different K-subset. This separates the post-incident tenant from the infrastructure they were previously sharing.

**Cost:** Rotation requires updating the routing mapping; in-flight requests must be allowed to complete on old shards before the cutover.

**How it backfires:** If the tenant's misbehavior is configuration-based (a bug in their code), rotating their shards only moves the problem. The fix must address root cause, not just blast radius.

## Interactions

- [Fair Scheduling](fair-scheduling.md) — shuffle sharding provides shard-level isolation; fair scheduling provides per-tenant queue-level isolation; both are needed in a multi-tenant system.
- [Consistent Hashing](../load-balancing/consistent-hashing.md) — the shard ring used in consistent hashing is the underlying structure; shuffle sharding picks K nodes from the ring rather than 1.
- [Correlated Failure](../dependencies/correlated-failure.md) — shuffle sharding limits blast radius; correlated failures (shared infrastructure failures) can override the isolation guarantee.
- [Bulkheads](../dependencies/bulkheads.md) — bulkheads isolate by failure domain; shuffle sharding isolates by tenant subset; both bound fault propagation.

## References

- MacCárthaigh, C. "Shuffle Sharding: Massive and Magical Fault Isolation." *AWS re:Invent 2014*.
  The original public description of shuffle sharding; includes the blast radius formula and production examples from Route 53.
- Amazon Web Services. "Shuffle sharding." *AWS Builders' Library*.
  Written version of the re:Invent talk; includes additional examples and implementation guidance.
