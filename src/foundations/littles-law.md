# Little's Law

> **L = λW** — the average number of requests in a system equals the arrival rate multiplied by the average time each spends there. This is a mathematical identity, not an approximation, and it holds regardless of arrival distribution, service distribution, or number of servers.

## The formula

**L** — average number of requests in the system at any moment (in queue + being served).  
**λ** — average arrival rate (requests per second).  
**W** — average time a request spends in the system (latency: queue wait + service time).

One identity, three observables. If you monitor all three, the product must hold in steady state. If it doesn't, you're not in steady state — you're either shedding load or accumulating a queue.

A service handling 500 RPS with an average latency of 200ms has:

> L = 500 × 0.2 = 100 in-flight requests

If average latency doubles to 400ms and nothing else changes, in-flight count doubles to 200. If in-flight count is bounded by a thread pool of 150, then λ must drop to 375 RPS instead — the service is now throttling itself.

## Why operators care

Little's Law makes three operational relationships precise:

**Dependency slowdown multiplies concurrency.** A downstream service that normally responds in 20ms starts responding in 200ms. At 1000 RPS, in-flight requests jump from 20 to 200. If the thread pool is sized at 50, the pool exhausts and the caller starts rejecting or queuing. This is how a slow downstream cascades into a caller failure — not because of errors, but because of latency multiplied by concurrency. See [Slow Is Worse Than Down](../patterns/dependencies/slow-is-worse-than-down.md).

**Thread pool sizing is a latency commitment.** A pool of N threads at arrival rate λ can handle average latency up to N/λ before saturating. A 50-thread pool at 500 RPS saturates when average latency reaches 100ms. If a dependency regularly hits 150ms at p99, the pool will be transiently full during those spikes, causing queuing behind it.

**Queue depth is a latency forecast.** By rearranging: W = L/λ. If a queue has 1000 items and drains at 200/s, items at the tail will wait 5 seconds. If your SLO is 2 seconds, those tail items are already dead. This is why [Queue Management](../patterns/overload/queue-management.md) uses queue depth as a shedding signal rather than waiting for requests to time out.

## The stability requirement

Little's Law requires a *stable* system: one where the arrival rate does not permanently exceed service capacity. In an unstable system, L grows without bound, W → ∞, and the steady-state assumption breaks.

Near the stability boundary (utilization ρ → 1), queuing theory shows that mean wait time grows as 1/(1-ρ). At 90% utilization, mean wait is 9× service time; at 99%, it's 99×. This is not a linear function of utilization — the last 10% of capacity is extremely expensive to use.

A consequence for provisioning: running at 80% utilization leaves a buffer for load variance; running at 95% guarantees that moderate spikes cause disproportionate latency increases. The right target utilization depends on how bursty the arrival process is and how tight the latency SLO is.

## A practical diagnostic

When something goes wrong, Little's Law gives you a consistency check. If your monitoring shows:
- λ = 400 RPS (stable)
- p50 latency = 250ms
- In-flight requests = 200

Then L = 400 × 0.25 = 100. But you observe 200. The discrepancy means either your latency measurement is wrong (it's higher than 250ms on average, not just at p50), you have stuck requests that aren't completing, or you're in a transient non-steady-state. Any of these is worth investigating.

## Connections to other foundations

Little's Law connects directly to [Goodput vs. Throughput](goodput-vs-throughput.md): the W in the formula is sojourn time in the system, but goodput only counts requests that exit with a successful response within their deadline. Requests that time out still counted toward L while in-flight, consuming capacity without contributing to goodput.

[Open vs. Closed Loop](open-vs-closed-loop.md) governs how λ behaves: in a closed loop, λ is bounded by the service's throughput; in an open loop, λ is independent, and the system must absorb it or reject it.

## References

- Little, J.D.C. "A Proof for the Queuing Formula: L = λW." *Operations Research* 9(3), 1961.
  The original proof. Remarkably short (one page) and accessible.
- Gunther, N.J. *Analyzing Computer System Performance with Perl::PDQ*. Springer, 2011.
  Chapter 2 applies queuing theory including Little's Law to practical capacity planning.
- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  The standard academic treatment; chapters 9–15 cover the stability boundary and its consequences.
