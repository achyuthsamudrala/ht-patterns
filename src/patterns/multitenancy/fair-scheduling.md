# Fair Scheduling

> **One-liner:** FIFO queues let any one tenant monopolize capacity when they run a burst of requests — weighted fair queuing gives each tenant its own virtual clock so bursts drain in isolation, not at each other's expense.

## Symptom

- A subset of tenants report consistently poor latency while aggregate throughput looks healthy.
- Bursty tenants see fast responses while steady tenants are delayed.
- Queue depth high for some tenants despite others being well below quota.
- In shared infrastructure: one team's batch job delays real-time serving traffic for others.

## Mechanism

**FIFO's structural unfairness:**

A single FIFO queue across tenants is unfair by design. A tenant that sends 100 requests in a burst occupies 100 queue slots, blocking all other tenants' requests behind it. Even if the bursting tenant is within its quota (quota measures how much they can consume, not how fast the queue drains), their burst degrades others.

```
Queue (FIFO): [T1, T1, T1, ..., T1×90, T2, T3, T2, T4, ...]
                 ^-- 90 T1 requests occupy the front of the queue
```

T2, T3, T4 are blocked behind T1's burst regardless of their priority or quota balance.

**Weighted Fair Queuing (WFQ) mechanics:**

WFQ assigns each tenant a virtual time. When a tenant submits a request, its virtual start time is:
```
virtual_start = max(last_virtual_finish[tenant], current_virtual_time)
virtual_finish = virtual_start + request_cost / weight[tenant]
```

The server always dequeues the request with the smallest virtual finish time. This ensures:
1. Each tenant gets a bandwidth share proportional to its weight.
2. Bursts are absorbed within the tenant's virtual queue, not across tenants.
3. An idle tenant's credits accumulate (up to a cap) and allow temporary bursts.

WFQ provides max-min fairness: no tenant receives more than its share when the system is overloaded; idle tenants' unused capacity is redistributed to active ones.

**Deficit Round Robin (DRR) as a practical approximation:**

WFQ has O(log N) scheduling overhead (heap on virtual finish times). DRR (Shreedhar & Varghese, 1995) approximates WFQ with O(1) per-request overhead:

Each tenant has a deficit counter. Each round, each tenant receives a quantum Q × weight[tenant]. If a request is smaller than the current deficit, it is served and the deficit is reduced. If larger, the deficit is carried to the next round. This gives proportional bandwidth allocation without the per-request sort.

**Why idle-time credit matters:**

WFQ and DRR both allow credit accumulation for tenants that are temporarily under their quota. A tenant that is idle for 10 seconds accumulates credit that it can use for a burst. The credit cap is critical: without it, a long-idle tenant returns and submits a massive burst that temporarily monopolizes the server. Set the credit cap at a small multiple of the per-request quota burst size.

## Real-world sightings

**Linux kernel CFQ (Completely Fair Queuing) I/O scheduler.** The Linux kernel uses CFQ for I/O scheduling, implementing per-process FIFO queues with a round-robin serving policy across processes. CFQ assigns time slices to each process and serves its queue within the slice; unused time within the slice is reallocated. This prevents any single process from monopolizing disk I/O.

**Apache Kafka consumer group scheduling.** Kafka consumer groups implement a form of fair scheduling across partitions: each consumer in a group is assigned a partition subset by the group coordinator, ensuring partitions are distributed relatively evenly. When one consumer is slow, the partition rebalance redistributes work. The broker itself does not implement WFQ, but partition-level isolation provides similar fairness guarantees.

## Mitigations

### Per-tenant queue with round-robin serving

**What it is:** Maintain a separate queue per tenant. A scheduler serves one request from each non-empty queue in round-robin order. This ensures no single tenant can block others regardless of burst size.

**Cost:** Memory proportional to number of active tenants × queue depth per tenant. Round-robin doesn't account for request cost heterogeneity (a large request from T1 is scheduled the same as a small request from T2 in unweighted round-robin).

**How it backfires:** Unweighted round-robin is unfair to tenants with different SLAs or weights. If tenant T1 pays for 10× more capacity than T2, they should receive 10× more throughput. Cost-weighted fairness (WFQ/DRR) is required for SLA-proportional allocation.

### Weighted Fair Queuing with virtual clocks

**What it is:** Implement WFQ: each tenant's request is tagged with a virtual finish time based on its cost and the tenant's weight. The scheduler always serves the request with the smallest virtual finish time. Weights encode the tenant's SLA (a premium tenant might have weight 10 vs a free-tier tenant's weight 1).

**Cost:** O(log N) scheduling overhead (heap). More complex to implement than round-robin.

**How it backfires:** WFQ is fair across tenants but not across request priorities within a tenant. A tenant's bulk background job can still delay their own interactive requests. Address with per-tenant priority classes.

### Credit caps on idle accumulation

**What it is:** Limit the credit a tenant can accumulate while idle. When a tenant's virtual finish time falls far behind the current virtual time (due to idleness), cap how far back it can "reach" — limit the burst the tenant can claim from accumulated credits.

**Cost:** Reduces the benefit of virtual time for bursty tenants; they may see slightly higher latency during their burst.

**How it backfires:** Without credit caps, a very-long-idle tenant can effectively jump to the front of the queue for a burst that exceeds what they would normally get — temporarily starving others.

## Interactions

- [Cost-Aware Quotas](cost-aware-quotas.md) — quotas bound total consumption; fair scheduling determines the order in which consumption happens; they work together.
- [Mixed Request Patterns](mixed-request-patterns.md) — fair scheduling across tenants; mixed request handling addresses fairness within a tenant's own request types.
- [Load Shedding](../overload/load-shedding.md) — when even fair scheduling cannot keep up, load shedding drops lower-priority requests to protect the system.

## References

- Shreedhar, M. and Varghese, G. "Efficient Fair Queuing Using Deficit Round-Robin." *IEEE/ACM TON*, 1996.
  The original DRR paper; the algorithm description is precise and directly implementable.
- Demers, A. et al. "Analysis and Simulation of a Fair Queuing Algorithm." *SIGCOMM 1989*.
  The original WFQ paper; introduces the virtual clock mechanism used in modern fair schedulers.
