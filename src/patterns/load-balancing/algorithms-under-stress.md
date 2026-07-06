# Algorithms Under Stress

> **One-liner:** Round-robin distributes requests evenly; least-connections distributes connections evenly — but neither distributes *work* evenly when requests have different costs or backends have different speeds.

## Symptom

- Some backends CPU-pegged or saturated; others idle — despite even request distribution at the load balancer.
- Backends with slower processing appear "busier" (more connections, higher latency) and receive the same number of requests as faster backends.
- After a GC pause on one backend, round-robin continues sending requests to it at the same rate; the backend builds a queue while recovering.
- Least-connections routes to a backend with 5 long-running connections ahead of one with 5 short-running connections, even though the second is effectively idle.

## Mechanism

**Round-robin (RR):** Distribute requests in a fixed cyclic order. Simple, predictable, and stateless. Each backend receives exactly 1/N of the traffic. Works correctly when:
- All requests have the same cost.
- All backends have the same processing capacity.
- No backend is slower than the others at any moment.

Fails when any of these assumptions break. A backend that is GC-pausing for 200ms receives the same traffic as healthy backends; it builds a queue during the pause. A backend processing large requests spends more time per request; it falls behind backends processing cheap requests.

**Least-connections:** Route to the backend with the fewest active connections. Better than RR for heterogeneous request cost — an overloaded backend naturally accumulates connections, receiving less new traffic. Fails when:
- Connections are held for different durations. Two long-held connections look identical to two short-held connections.
- Long-lived streaming connections inflate connection counts without proportional work.
- Connection reuse (HTTP/2 multiplexing) means connection count is decoupled from request count.

**Power of Two Choices (P2C) / Least-Outstanding Requests:**

Sample two backends uniformly at random. Send the request to the one with fewer outstanding requests (in-flight, not connections). This has provably better worst-case load distribution than either RR or least-connections:

- RR worst case: O(log N / log log N) load imbalance.
- P2C worst case: O(log log N) load imbalance (for N backends).

The intuition: random sampling avoids the global coordination needed for "least globally," while sampling two (rather than one) provides exponential improvement over pure random choice.

**Latency-weighted routing (EWMA):** Track each backend's exponentially-weighted moving average of response time. Weight routing probability inversely proportional to EWMA latency. Backends that are slow receive less traffic; backends that are fast receive more. This adapts to both load-induced slowness (overloaded backend → slow EWMA → fewer requests) and capacity heterogeneity (faster hardware → faster EWMA → more requests).

**Comparison at saturation:**

| Algorithm | Under homogeneous load | Under heterogeneous cost | Under backend slowness |
|-----------|----------------------|------------------------|----------------------|
| Round-robin | Correct | Poor | Poor |
| Least-connections | Good | Moderate | Good (with reuse) |
| P2C (least-outstanding) | Good | Good | Good |
| EWMA latency-weighted | Good | Good | Best |

## Real-world sightings

**Mitzenmacher, M. "The Power of Two Choices in Randomized Load Balancing" (IEEE TPDS 2001).** The theoretical foundation for P2C. Proves that sampling two backends and choosing the less-loaded one achieves O(log log N) max load, vs. O(log N / log log N) for random (equivalent to RR). The result is that the second sample provides disproportionate improvement over one sample — hence "power of two."

**Envoy Proxy load balancing documentation.** Envoy implements least-request (equivalent to P2C least-outstanding) as its recommended L7 load balancing algorithm. The documentation notes that least-request is superior to round-robin for most service-to-service communication because request costs are rarely uniform.

**Twitter Finagle.** Finagle uses EWMA-based latency-weighted routing (described in "The Waterfall of Code" post by Marius Eriksen), tracking each backend's response time and adjusting routing weights. The system automatically reduces traffic to degraded backends before they become saturated.

## Mitigations

### P2C / least-outstanding-requests

**What it is:** On each request, sample two backends uniformly at random (from the healthy pool). Send to the one with fewer in-flight requests.

**Cost:** Requires accurate per-backend in-flight tracking; O(1) per routing decision.

**How it backfires:** In-flight count doesn't account for request cost. Two in-flight heavy requests look the same as two in-flight light requests. Under extremely heterogeneous request cost, EWMA latency-weighted routing is better.

### EWMA latency-weighted routing

**What it is:** Maintain an exponentially-weighted moving average of response latency for each backend. On each request, route to the backend with the lowest EWMA latency (weighted by a small factor for randomness). Update the EWMA on each response completion.

**Cost:** Requires per-backend latency tracking; routing decisions are probabilistic rather than deterministic.

**How it backfires:** EWMA is a lagging indicator — a backend that suddenly slows (GC pause) continues receiving traffic at the old weight until enough responses complete to update the EWMA. The lag is proportional to the EWMA window size.

### Slow-start for new backends

**What it is:** When a new backend is added to the pool, ramp its routing weight gradually from 0 to full weight over a warm-up period. This prevents the connection storm and initial load spike that would occur if the new backend immediately received 1/N of traffic.

**Cost:** The new backend doesn't contribute full capacity until fully warmed. More code complexity in the load balancer.

**How it backfires:** If the warm-up period is too long, newly added capacity takes too long to absorb load during a traffic spike that triggered the scale-out.

## Interactions

- [Health Checking](health-checking.md) — unhealthy hosts must be excluded from the P2C sample before routing decisions.
- [Consistent Hashing](consistent-hashing.md) — consistent hashing sacrifices even load distribution for key locality; P2C sacrifices locality for even distribution. They are typically not combined directly.
- [Fanout Amplification](../tail-latency/fanout-amplification.md) — load balancing algorithm choice affects how evenly sub-request latency is distributed across shards, which in turn affects the maximum.

## References

- Mitzenmacher, M. "The Power of Two Choices in Randomized Load Balancing." *IEEE Transactions on Parallel and Distributed Systems* 12(10), 2001.
  Foundational theory for P2C; proves the O(log log N) bound.
- Envoy Proxy. "Load Balancing." https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/load_balancing/overview
  Practical implementation of P2C (least-request) and EWMA-based routing in a production proxy.
- Eriksen, M. "Your Server as a Function." *WOOT 2013*.
  Describes Finagle's latency-weighted routing and the operational justification for preferring it over connection-count-based algorithms.
