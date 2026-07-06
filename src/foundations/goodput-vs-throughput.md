# Goodput vs. Throughput

> Accepted RPS and completed-within-SLO RPS are the same under light load and diverge catastrophically under overload. Monitoring only one while operating near saturation is like measuring fuel in the intake instead of at the engine.

## Definitions

**Throughput:** The rate at which the service accepts requests — requests entering the system per second. In an open-loop system, the server cannot reject arrivals without an explicit mechanism; throughput may stay high even as the service degrades.

**Goodput:** The rate at which the service delivers useful responses — requests successfully completed within their deadline per second. A request that times out, returns an error, or completes after the client has already given up does not count toward goodput.

Under light load, every accepted request completes successfully and within its deadline. Throughput = goodput. As load increases toward saturation, the gap opens.

## The collapse curve

A server has finite processing capacity C (requests per second). When offered load λ exceeds C, a queue forms. Queue length grows at rate (λ - C). Each request waits longer before being served. Eventually, requests wait longer than their deadline and expire. The server then does work on requests whose clients have already timed out and moved on — consuming CPU and memory for output that will never be delivered.

The shape of goodput vs. offered load is characteristic:

- **λ < C:** Goodput ≈ λ. The service handles all offered load.
- **λ ≈ C:** Goodput begins to fall below λ as queueing latency starts to push the tail over the deadline.
- **λ >> C:** Goodput collapses. The server is maximally busy but producing little useful output. Adding more load at this point does not reduce goodput further (the server is already saturated) but does increase the queue of dead work.

The `goodput_collapse` figure in [Goodput Collapse](../patterns/overload/goodput-collapse.md) shows this shape for an M/M/c queue with timeout.

## Why standard metrics hide this

A dashboard showing "10,000 RPS" looks healthy. But if the chart shows *accepted* RPS and 8,000 of those requests are timing out, the service is delivering 2,000 RPS of goodput while burning capacity on 8,000 RPS of dead work. Standard RPC monitoring often captures one of these numbers:

- **Incoming request rate:** Acceptances, often from load balancer metrics. Does not capture timeouts.
- **Outgoing response rate:** Responses the server sends, including error responses. Does not distinguish within-SLO from beyond-SLO.
- **Client-side success rate:** Correct but only visible to callers, not to the server itself.

The fix is to instrument the gap explicitly:

```
# Server-side instrumentation
requests_accepted_total          # arrival rate
requests_completed_total         # responses sent (success + error)
requests_completed_within_slo    # successful responses where latency < deadline
```

Goodput = `requests_completed_within_slo / time_window`. The gap between accepted and completed-within-SLO is wasted capacity.

## The waste trap at high load

There is a counterintuitive feedback loop under extreme overload:

1. Server is above saturation; queue depth is D items.
2. Requests at the tail of the queue have deadline < queue drain time; they will time out.
3. Server processes them anyway (it doesn't know they've timed out unless deadlines are propagated — see [Deadline Propagation](../patterns/overload/deadline-propagation.md)).
4. Processing dead work consumes capacity that could serve live requests.
5. Live requests queue longer, more of them expire, increasing the fraction of dead work.

At extreme overload, this loop drives goodput toward zero while throughput (CPU utilization) stays at 100%. The server is maximally busy and producing nothing useful.

Mitigations that break this loop: deadline-aware queuing (discard expired requests), load shedding (reject at the entry point before queueing), and LIFO queue discipline (serve newest first, so older expired work is naturally deprioritized).

## Goodput in inference serving

Token generation creates a richer goodput definition. A request that generates 500 tokens but the client expected 1,000 (due to preemption or memory pressure) is partial goodput. The inference-specific dimensions:

- **TTFT SLO:** Did the first token arrive within the deadline? A response that passes TTFT but fails ITL (inter-token latency) is still degraded goodput.
- **Output completeness:** Did the response terminate naturally or was it truncated?
- **Token throughput:** Tokens delivered per second per GPU is the goodput metric for throughput-optimized inference, not requests per second.

See [Token-Level SLOs](../patterns/inference/token-level-slos.md) for the full treatment.

## The provisioning implication

Goodput collapse means that provisioning for peak throughput is insufficient if the peak creates near-saturation conditions. At 95% utilization, moderate load spikes push the service over the saturation knee and goodput falls nonlinearly. The correct provisioning target is the utilization at which goodput remains stable under your actual load variance — typically 60–70% of maximum throughput for bursty open-loop traffic.

Running at 80% of maximum throughput provides some burst headroom but may still enter goodput collapse during a 2× traffic spike. Running at 50% provides more headroom at a higher idle cost. The right number depends on burst shape, spike duration, and the cost of degradation.

## References

- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  Chapter 28 covers the heavy-traffic approximation and the behavior of effective throughput near saturation.
- Hamilton, J. "On Designing and Deploying Internet-Scale Services." *USENIX LISA*, 2007.
  Section 3 discusses capacity planning and the difference between peak load and sustainable load.
