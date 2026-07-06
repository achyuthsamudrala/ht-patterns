# Goodput Collapse

> **One-liner:** Past the saturation point, accepting more work produces less useful output — throughput stays high while goodput falls to near zero.

## Symptom

- p99 and p50 both rising together (not diverging — all requests slow).
- CPU at or near 100%; request queue depth growing monotonically.
- Accepted RPS is stable or rising; completed-within-SLO RPS is falling.
- Error rate (timeouts, 503s) increasing monotonically as requests expire their deadlines.
- After the load spike passes, recovery is slow — the queue continues draining and latency stays elevated for minutes.
- Dashboards show "high RPS" but downstream systems report the service as effectively unavailable.

## Mechanism

A server with c workers processes requests at a maximum rate C = c × μ (where μ is the per-worker service rate). When offered load λ exceeds C, a queue forms and grows at rate (λ − C). Each request in queue waits longer before being served. When wait time exceeds the request's remaining deadline, the request expires — but the server doesn't discover this until it finishes processing (unless [Deadline Propagation](deadline-propagation.md) is implemented).

The result: the server expends capacity processing requests that have already been abandoned by their callers. This waste reduces the capacity available for live requests, causing more requests to expire, increasing the waste fraction further. At extreme overload, the server is maximally busy and delivering near-zero goodput.

![Goodput vs. offered load. As offered load exceeds capacity (λ/C > 1), goodput collapses. Shorter request timeouts collapse the curve earlier but also recover faster once load drops. Without timeouts, goodput equals min(λ, C) and doesn't collapse — but the client waits indefinitely.](../../figures/goodput_collapse/goodput_collapse.svg)

*Figure: Goodput (fraction of capacity) vs. normalized offered load (λ/C) for an M/M/c queue with per-request timeout. At λ/C < 1, goodput ≈ offered load. Past saturation, the collapse is rapid. A timeout of 3× mean service time begins collapsing at λ/C ≈ 0.95; a timeout of 10× doesn't collapse until λ/C ≈ 1.5 but falls further before recovering.*

The shape of the curve explains why overloaded services feel binary to users: response time is fine, then suddenly every request is timing out. There's no gradual degradation — the queue fills, the tail explodes, and the service is effectively down even though CPU and accepted RPS look normal.

Two aggravating factors make the collapse self-sustaining:

**Retry amplification.** When requests time out, callers retry. Retries arrive as additional open-loop load on an already-saturated server, pushing λ further above C. The server gets busier, more requests expire, more retries arrive. See [Retry Storms](retry-storms.md) and [Metastable Failures](metastable-failures.md).

**Zombie work.** Without deadline propagation, the server processes requests that expired minutes ago. The wasted capacity is proportional to the depth of the expired-request backlog. At extreme overload, most of the server's capacity is spent on dead work.

## Real-world sightings

**Amazon Builders' Library.** The AWS essay "Using load shedding to avoid overload" describes the exact goodput-collapse mechanism in production terms: a service that accepts all requests queues work it cannot complete within the client's timeout, wastes CPU on those requests after they've timed out, and delivers close to zero goodput despite 100% CPU utilization. The essay describes this as the failure mode that makes load shedding necessary — not just useful, but *necessary*, because without shedding a service under sufficient overload cannot self-recover.

**Queueing theory.** The collapse curve is derivable from first principles using M/D/c and M/M/c queuing models with deadlines (Harchol-Balter, Chapter 28). The key insight is that the mean number of requests in the system diverges as ρ → 1, so a moderate overload (λ = 1.1C) causes sojourn times well above the deadline for the average request. This is not a theoretical curiosity — it describes what real services experience under load.

No single public postmortem frames the phenomenon explicitly as "goodput collapse" — affected services report it as "the service was down" or "latency spiked to 30 seconds." The offered-load mechanism is inferred from CPU and queue depth metrics after the fact.

## Mitigations

### Load shedding

**What it is:** Reject requests at the entry point when queue depth, in-flight count, or CPU exceeds a threshold. Return a fast 429 or 503 rather than queueing work that will time out anyway.

**Cost:** Clients see explicit errors under load, which requires the caller to handle overload explicitly. Adds a rejection decision on every request path.

**How it backfires:** If the shedding signal lags the actual overload (e.g., CPU-based shedding when the bottleneck is IO), shedding starts too late. If the threshold is too aggressive, the service sheds during normal burst traffic. See [Load Shedding](load-shedding.md) for full treatment.

### Concurrency limits

**What it is:** Bound the number of in-flight requests. Requests beyond the limit are rejected immediately rather than queued.

**Cost:** Adds admission overhead; the limit requires tuning.

**How it backfires:** A static limit tuned for normal processing time becomes too low when processing time increases under stress, rejecting requests that could succeed. See [Adaptive Concurrency](adaptive-concurrency.md) for the dynamic alternative.

### Deadline-aware queue drain

**What it is:** Before serving a queued request, check whether it has remaining deadline. Discard expired requests immediately without processing them.

**Cost:** Requires per-request deadline metadata in the queue; adds a check on dequeue.

**How it backfires:** If deadline metadata is absent or incorrect (clock skew, missing propagation), live requests can be discarded. See [Deadline Propagation](deadline-propagation.md).

## Interactions

- [Retry Storms](retry-storms.md) — timed-out requests generate retries, amplifying λ and deepening the collapse. The most common path from goodput collapse to metastability.
- [Metastable Failures](metastable-failures.md) — goodput collapse transitions to metastability when retries sustain overload after the original load spike has passed.
- [Queue Management](queue-management.md) — LIFO and CoDel limit the depth of expired-request backlog, containing the waste feedback loop.
- [Adaptive Concurrency](adaptive-concurrency.md) — the mitigation that bounds in-flight count to prevent collapse without a static threshold.

## References

- Amazon Web Services. "Using load shedding to avoid overload." *AWS Builders' Library*.
  The practical reference for this pattern; describes the mechanism and the mitigation hierarchy.
- Harchol-Balter, M. *Performance Modeling and Design of Computer Systems*. Cambridge, 2013.
  Chapter 28 derives the collapse curve analytically; Chapter 29 covers the M/G/k/k loss system.
- Brooker, M. "Metastable Failures in the Wild." *OSDI 2022*.
  Section 2 describes goodput collapse as a precursor to self-sustaining failure loops.
