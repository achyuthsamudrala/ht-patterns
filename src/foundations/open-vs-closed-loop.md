# Open vs. Closed Loop

> Most load tests are closed-loop. Most production traffic is open-loop. The difference determines whether your test finds overload behavior before or after your users do.

## Definitions

**Closed-loop system:** The next request is sent only after the previous one completes. A load test with 100 concurrent threads, each issuing requests serially, is closed-loop. If the service slows down, the effective arrival rate drops because threads are blocked waiting.

**Open-loop system:** Requests arrive according to an external process independent of the service's processing rate. Real users don't wait for your server's response before deciding to click. A Poisson arrival process (λ arrivals per second, regardless of service state) is the canonical model.

## What closed-loop tests hide

In a closed-loop test with N concurrent clients, the maximum arrival rate is N / W, where W is the current average latency. If the service slows (W increases), the arrival rate automatically drops. The system is *self-regulating*: you can never send more load than the service can process.

This property makes the test misleading in two ways:

**It underestimates load at high utilization.** At 95% CPU, the service is slow. In a closed-loop test, the slow service means slow threads, which means fewer requests per second, which means CPU drops. The test finds a stable equilibrium. In production, users don't back off — arrivals continue at full rate, and the queue grows.

**It misses the overload cliff.** A service under open-loop overload can reach a state where goodput collapses: CPU is high, queue is deep, requests are timing out, but the server is busy consuming capacity on work that will never complete. A closed-loop test cannot reach this state because the test's own latency increase reduces its arrival rate before the cliff is reached. See [Goodput Collapse](../patterns/overload/goodput-collapse.md).

## A concrete example

Consider a service with maximum throughput of 1000 RPS. Run two tests at a target of 1100 RPS:

- **Closed-loop test with 200 threads:** Threads pile up. Latency rises to 200ms. Rate drops to 200/0.2 = 1000 RPS. The service looks stable at "1000 RPS and 200ms latency." No errors.

- **Open-loop test at 1100 RPS:** Queue builds at 100 RPS excess. After 30 seconds, queue depth = 3000 requests. Requests start timing out. Error rate climbs. CPU stays at 100% processing dead work. Goodput collapses.

The closed-loop test reports "healthy at 1000 RPS." The open-loop test finds the failure mode.

## The right model for your service

Most service-to-service calls behave like closed loops at the individual connection level but like open loops at the client-fleet level. If 1000 clients each have 10 in-flight requests, you have an effective N of 10,000. The arrival rate from the fleet is not bounded by any one client's wait time.

User-facing traffic (browsers, mobile apps) is more open-loop than closed. A user who hits a slow page may wait a few seconds, then reload — which is a *retry*, not a backoff. That retry is additional open-loop load arriving on an already-slow service.

## Practical implications

**For load testing:** Use tools that generate open-loop arrivals. `wrk2` (based on Coordinated Omission correction), `hey`, Locust with constant arrival rate, or `ghz` for gRPC. Avoid tools that only measure "requests completed per second" (ab, basic wrk) — they are closed-loop generators by default and apply Coordinated Omission, underreporting tail latency.

**Coordinated Omission** is the specific bug in closed-loop latency measurement: when a service is slow, the test client doesn't send the next request, so the "latency" of that window is measured as only the slow response, not the long wait that would have occurred for requests that couldn't even start. The correct measurement includes all the requests that *would have been sent* during the slow window, each with a latency equal to the full blocked duration.

**For capacity planning:** Calculate your maximum closed-loop and open-loop estimates separately. The open-loop estimate is the one that matters when your service is under stress.

**For SLO commitments:** A p99 latency SLO measured under closed-loop test conditions will be violated under open-loop production load at the same nominal request rate. Measure the SLO under open-loop arrivals, at the target RPS, including the tail behavior at and above the saturation point.

## The connection to Little's Law

In a closed-loop system with N clients: L = N (constant, by construction). Little's Law says W = L/λ = N/λ, so W and λ are inversely related — when the server slows, λ drops automatically.

In an open-loop system: λ is fixed externally. L = λW can grow without bound as W increases. The only bound on L is the queue capacity or the arrival timeout. This is why open-loop overload accumulates: L keeps growing until something breaks (OOM, timeout, explicit rejection).

## References

- Schroeder, B., Wierman, A., and Harchol-Balter, M. "Open Versus Closed: A Cautionary Tale." *USENIX NSDI 2006*.
  The paper that named and formalized the problem. Shows that systems designed for closed-loop traffic fail when exposed to open-loop load even at the same nominal rate.
- Tene, G. "How NOT to Measure Latency." Talk at Strange Loop 2015.
  The canonical explanation of Coordinated Omission; covers why most latency benchmarks are wrong and how to fix them.
- Cockcroft, A. "Throughput and Latency." Medium, 2016.
  Short, practical treatment of the same ideas with concrete tool recommendations.
