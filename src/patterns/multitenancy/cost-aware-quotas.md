# Cost-Aware Quotas

> **One-liner:** A quota counted in requests hides wildly different costs — a "1000 RPS" limit that allows 1000 × 10MB uploads is a 10 GB/s flood; quota in resource units prevents this while request-count quotas invite gaming.

## Symptom

- A single tenant consuming a small fraction of request quota but a large fraction of compute time, memory, or bandwidth.
- Quotas appear underutilized in aggregate but the system is saturated at one resource.
- Light users complain of degradation despite low apparent load — their requests queue behind heavy ones.
- Gaming: a user stays under request quota by sending very large or very complex requests.

## Mechanism

**Why request-count quotas fail for heterogeneous workloads:**

Request count is a proxy for resource consumption. The proxy is accurate only when all requests have similar cost. When requests have heterogeneous cost, a per-request quota is exploited by sending fewer, larger requests.

Consider a transcription API:
- Small file (10 seconds audio): 1 API call, 0.1 CPU-seconds.
- Large file (3 hours audio): 1 API call, 72 CPU-seconds.

A 100 request/hour quota allows either 100 × 0.1 = 10 CPU-hours, or 100 × 72 = 7,200 CPU-hours. One user sending 100 small files and another sending 100 large files consume wildly different resources while showing the same quota usage.

**Cost units as the quota currency:**

The fix is to define a quota in terms of resource units that approximate actual cost. Token budgets for LLM APIs, capacity units for compute APIs, and dollar amounts for cloud billing are all forms of cost-aware quotas.

LLM API example:
- Input token: 1 unit.
- Output token: 3 units (more expensive, involves generation).
- Per-request quota: 10,000 units.
- A short completion (100 input, 50 output = 100 + 150 = 250 units) consumes 2.5% of the per-request quota.
- A long completion (5,000 input, 1,000 output = 5,000 + 3,000 = 8,000 units) consumes 80%.

This allocates capacity proportionally to actual compute consumed.

**Token bucket on cost units:**

The standard enforcement mechanism is a token bucket where tokens represent cost units:

```
on request arrival:
    cost = estimate_cost(request)  // measure or estimate before admission
    tokens = bucket.peek()
    if tokens < cost:
        return 429 Too Many Requests
    bucket.consume(cost)
    admit request
    // optionally adjust after completion: consume(actual_cost - cost)
```

The challenge: cost must be estimated before processing. Estimation may be inaccurate for variable-cost operations (e.g., the actual output length of an LLM completion is not known until generation is complete).

**Post-hoc vs pre-admission counting:**

*Pre-admission (pessimistic):* estimate cost before accepting the request; reject early if insufficient quota. Problem: estimates may be inaccurate, especially for LLM output length.

*Post-hoc:* admit all requests; deduct actual cost after completion. Problem: a tenant may overshoot their quota before the system can react; burst abuse is possible.

*Hybrid:* estimate and pre-deduct a minimum cost; top-up with actual cost delta after completion. This provides real-time enforcement while using accurate post-hoc costs.

## Real-world sightings

**OpenAI API token rate limits.** OpenAI enforces rate limits in both requests-per-minute and tokens-per-minute (TPM). The TPM limit directly implements cost-aware quotas: a request consuming 100K tokens uses 100× more quota than a request consuming 1K tokens. This prevents users from reaching request limits via short requests while others consume all compute via long ones.

**Google Cloud Bigtable "capacity units."** Bigtable documents its pricing and quota model in read capacity units (RCUs) and write capacity units (WCUs), where a unit corresponds to approximately 4KB of data. Rather than counting operations, Bigtable tracks data transferred, which better approximates actual I/O cost.

## Mitigations

### Request cost estimation before admission

**What it is:** Classify or estimate request cost before admission. For LLM APIs: measure input token count (known before generation); use a heuristic for output length (based on max_tokens parameter or past distributions). For batch jobs: measure data size or operation count from the request payload.

**Cost:** Requires cost estimation logic; estimates may be wrong. Must maintain token bucket accounting per tenant.

**How it backfires:** Under-estimation allows quota overshoot. Over-estimation rejects valid requests. For variable-cost operations, cost estimation is inherently uncertain.

### Actual cost feedback and post-hoc adjustment

**What it is:** Record the actual cost of each request after completion. If the actual cost differs from the pre-admitted estimate, adjust the tenant's quota bucket accordingly. This provides accurate long-run accounting even if individual estimates are noisy.

**Cost:** Increases accounting complexity (two debits per request: estimated pre-admission, actual post-completion). Requires storing in-flight estimated costs and reconciling them.

**How it backfires:** Post-hoc adjustments cannot prevent burst abuse during the window between admission and adjustment. A tenant can deplete all quota via a burst of large requests before adjustments catch up.

### Request size caps and admission control

**What it is:** Apply hard limits on individual request cost — a maximum file size, maximum batch size, or maximum token count per request. Cost-aware quotas control aggregate consumption; size caps control individual request blast radius.

**Cost:** Forces users to split large operations; adds round-trip overhead.

**How it backfires:** Size caps encourage users to split operations into many same-size chunks, which may increase overhead (per-request amortization costs) without reducing aggregate resource consumption.

## Interactions

- [Fair Scheduling](fair-scheduling.md) — cost-aware quotas determine *how much* each tenant can consume; fair scheduling determines *when* they consume it; both together are needed.
- [Mixed Request Patterns](mixed-request-patterns.md) — large requests from one tenant block small requests from others when not properly isolated.
- [Adaptive Concurrency](../overload/adaptive-concurrency.md) — cost-aware quotas set per-tenant limits; adaptive concurrency sets system-wide limits; both enforce at different scopes.

## References

- OpenAI. "Rate limits." *OpenAI API Documentation*.
  Describes both RPM and TPM limits; the TPM limit is the canonical cost-aware quota example.
- Kleppmann, M. *Designing Data-Intensive Applications*. O'Reilly, 2017.
  Chapter 12 discusses fairness and prioritization in data systems; cost-aware accounting is discussed in the context of resource allocation.
