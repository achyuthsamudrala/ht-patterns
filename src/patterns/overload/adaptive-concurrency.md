# Adaptive Concurrency

> **One-liner:** A static concurrency limit tuned at steady state is wrong the moment processing time changes — an adaptive limit uses measured latency to track actual capacity in real time.

## Symptom

*Static limit too high (service underprotected):*

- Under load, queue builds beyond the concurrency limit's expected effect.
- p99 rising past the SLO while in-flight count is below the limit.
- Limit was set during low-load tuning; service is slower under production load.

*Static limit too low (service over-throttled):*

- CPU and connections idle; in-flight requests queued at the admission point.
- Throughput plateaued below what hardware can support.
- Limit doesn't adjust as the service gets faster after a downstream recovery.

*Well-functioning adaptive concurrency:*

- In-flight count fluctuates around a value that tracks actual server capacity.
- p99 stable across a wide range of offered loads.
- Limit rises when the service gets faster; falls when it gets slower.

## Mechanism

Adaptive concurrency limits infer the optimal in-flight count from observed latency rather than requiring a pre-set value.

The foundation is [Little's Law](../../foundations/littles-law.md): **L = λW**. At the server's uncongested processing speed, each request takes W_min seconds. The optimal number of in-flight requests to keep the server busy without causing queuing is:

> **L_opt ≈ λ × W_min**

When L > L_opt, requests are spending time in a queue rather than being served. Reducing L toward L_opt eliminates the queuing component of latency.

**The gradient-based algorithm (Netflix Concurrency Limits):**

At each request completion, compute:
- `gradient = W_min / W_measured`
- New limit = limit × gradient + headroom

When W_measured > W_min (server is slower than baseline), gradient < 1, limit decreases. When W_measured ≈ W_min (server is at baseline), gradient ≈ 1, limit stays constant. A headroom term (typically √limit) allows gradual growth when the server is fast.

The gradient uses the minimum observed latency (over a time window) as a proxy for W_min. This requires that W_min be observable — a service that is always under load will never see W_min, and the gradient will be computed against a baseline that's already congested.

**AIMD (Additive Increase, Multiplicative Decrease):**

Modeled on TCP congestion control:
- Each success increases the limit by a small additive amount.
- Each timeout/rejection decreases the limit multiplicatively.
- Produces saw-tooth behavior around the optimal value.

AIMD is more conservative than gradient-based control and more robust to measurement noise, but converges more slowly to the correct limit.

**The Little's Law connection makes the optimum precise.** A service handling 200 RPS at 50ms uncongested latency has L_opt = 200 × 0.05 = 10 in-flight requests. If you observe 50 in-flight requests at 250ms latency, you're queuing 40 requests (4× the optimal) and 4× of your observed latency is queue wait. Reducing the limit from 50 to 10 would eliminate the queue and drop latency from 250ms to 50ms while maintaining throughput.

## Real-world sightings

**Netflix, "Performance Under Load" (2018).** Netflix's engineering blog describes the gradient-based adaptive concurrency limit as a replacement for static thread pool limits in their microservice architecture. The post reports that static limits tuned for normal load under-protect services during traffic spikes (the limit is high enough that the service collapses before it kicks in) while over-protecting during low-latency periods (the limit prevents the service from using available capacity). The adaptive version maintained stable p99 across traffic variation with no manual tuning.

**Netflix concurrency-limits library.** The open-source library (github.com/Netflix/concurrency-limits) implements gradient, AIMD, and Vegas-based algorithms. It is integrated with gRPC, Servlet, and Hystrix. The README provides benchmarks showing the gradient algorithm tracking capacity changes within a few hundred requests.

## Mitigations

### Gradient-based limit (for latency-sensitive services)

**What it is:** Adjust the concurrency limit based on the ratio of minimum observed latency to current latency. The limit tracks available capacity in near real time.

**Cost:** Requires accurate latency measurement; susceptible to noise from unrelated latency sources (GC, garbage spikes).

**How it backfires:** If W_min is measured during a period when the service is already under load, the baseline is wrong and the limit will be set too high. The algorithm should reset W_min periodically to allow it to fall when the service speeds up.

### AIMD limit (for error-rate-sensitive services)

**What it is:** Increase the limit additively on success; decrease multiplicatively on timeout or error.

**Cost:** Converges slowly to the optimum; produces sawtooth around the ideal limit.

**How it backfires:** AIMD responds to errors and timeouts, not to latency increase. A service that is getting slower but not yet erroring will not trigger AIMD reduction.

### Vegas-inspired limit (hybrid)

**What it is:** Based on TCP Vegas: compare actual throughput to the throughput that would be achieved without congestion. Reduce the limit when the ratio falls below a threshold.

**Cost:** Throughput estimation requires more history; more parameters to tune.

**How it backfires:** Throughput estimate noise from bursty arrivals can cause the limit to oscillate.

## Interactions

- [Goodput Collapse](goodput-collapse.md) — adaptive concurrency limits are the primary structural defense against collapse without a static limit.
- [Load Shedding](load-shedding.md) — adaptive concurrency provides the signal; load shedding is the action.
- [Queue Management](queue-management.md) — concurrency limit and queue depth together determine how many requests are in the system at any time.

## References

- Netflix. "Performance Under Load." *Netflix Engineering Blog*, 2018.
  Describes the gradient-based algorithm and production results; includes benchmark comparisons to static limits.
- Brooker, M. "Controlled Concurrency." *brooker.co.za/blog*, 2020.
  Analyzes adaptive concurrency limit algorithms and their relationship to TCP congestion control; identifies failure modes.
- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  Chapter 26 covers admission control policies; provides the theoretical basis for why optimal in-flight count follows Little's Law.
