# Health Checking

> **One-liner:** Health checks that eject failing hosts protect healthy traffic, but a threshold calibrated for single-host failures will eject every host when the trigger is a global event — the "everyone ejects everyone" cascade.

## Symptom

- All backends ejected from load balancer pool simultaneously; service returns to normal immediately on manual reset (hosts were not actually sick).
- Health check failures correlated with a global event: network blip, shared dependency slowdown, deployment, or config push.
- Error rate during the ejection window is higher than the error rate that triggered ejection — because routing to zero hosts produces 100% errors.
- Individual host metrics (CPU, memory, connection count) show hosts were healthy when ejected.

*Well-functioning health checking:*
- Individual slow or failing hosts are ejected; traffic redistributes to remaining healthy hosts without error rate impact.
- Ejected hosts recover and are re-admitted automatically; the ejection window is short.

## Mechanism

**Outlier ejection mechanics:** The load balancer monitors each backend's error rate and latency. When a backend's metrics exceed a threshold:
- Error rate > X% over a rolling window.
- Latency p99 > Y ms sustained for Z seconds.

The backend is ejected from the pool: no new requests are routed to it for a penalty period. After the penalty period, the backend is probed; if healthy, it re-enters the pool.

**The global-event cascade:**

1. A global event begins: a shared dependency slows, network latency spikes briefly, or a new config causes a brief error burst.
2. All backends experience elevated error rates simultaneously (the event is global, not host-specific).
3. Error rate exceeds the ejection threshold on backend A → ejected. Traffic redistributes to B, C, D... increasing their load.
4. Higher load on remaining backends increases their error rates, pushing them over the threshold → ejected.
5. Cascades until all backends are ejected or the ejection percentage cap triggers.
6. With no backends in the pool, 100% of requests fail. Error rate is now 100%, worse than the 5% that triggered ejection.

**The ironically named "panic mode":** Envoy's term for the state where too many backends have been ejected and the load balancer "panics" — reverting to routing to all backends including the ejected ones, on the grounds that some service is better than none. This is a safety valve that prevents the zero-healthy-backends case.

**Active vs. passive health checking:**

*Passive (outlier detection):* Monitor real traffic; eject based on observed error/latency. Low overhead; reacts to actual production failures. The cascade risk above applies.

*Active (health probes):* The load balancer periodically sends synthetic health probes (HTTP GET /health, TCP connect, gRPC health check). A backend that fails to respond to probes is ejected. More reliable for detecting backends that are up but not processing traffic; does not observe application-level failures.

*Hybrid:* Use active probes to detect host-level failures (process crash, host down) and passive outlier detection to detect application-level degradation. Set separate thresholds for each.

**Ejection percentage cap:** The most important configuration parameter for preventing the cascade. Never eject more than max_ejection_percent (e.g., 50%) of the pool at once. If the ejection algorithm would eject 80% of the pool, it only ejects 50%. The remaining 30% stay in the pool and continue serving traffic despite their elevated error rates.

The tradeoff: the cap allows unhealthy backends in the pool, but avoids the worse outcome of zero backends.

## Real-world sightings

**Envoy Proxy outlier detection documentation.** Envoy's outlier detection implements the ejection percentage cap, consecutive error count thresholds, and panic mode as first-class features. The documentation explicitly describes the cascade risk and recommends the cap as the primary defense. Envoy's defaults (max_ejection_percent=10) are deliberately conservative to prevent cascades.

**Beyer et al., "Site Reliability Engineering" (2016).** Chapter 22 describes the "oscillating health check" failure mode at Google: health checks that are too sensitive cause repeated ejection-and-readmission cycles, driving load between a small set of hosts and eventually saturating each one in turn. The chapter recommends hysteresis in health check thresholds (require health to be stable before re-admission).

## Mitigations

### Ejection percentage cap

**What it is:** Limit the fraction of backends that can be simultaneously ejected to max_ejection_percent (e.g., 50%). The ejection algorithm checks this cap before each ejection; if already at the cap, the backend is not ejected even if its metrics exceed the threshold.

**Cost:** Allows some unhealthy backends to remain in the pool when the cap is hit.

**How it backfires:** If more than max_ejection_percent of backends are genuinely unhealthy (e.g., a bad deploy to 80% of the fleet), the cap allows the unhealthy backends to remain in the pool, causing elevated error rates even though healthy backends could serve all traffic.

### Panic mode routing

**What it is:** When the healthy pool drops below a minimum threshold (e.g., 20% of backends), revert to routing to all backends including ejected ones. Report the panic mode state via metrics and alerts.

**Cost:** Sends some traffic to backends that are in the ejected state — may worsen their condition.

**How it backfires:** Panic mode under a genuine partial failure (10% of backends truly down) routes some traffic to the down backends. The alternative (zero-backend routing) is worse, but panic mode should alert, not silently degrade.

### Differentiated thresholds for active vs. passive

**What it is:** Set conservative thresholds for passive outlier ejection (requiring sustained failure over a longer window); set aggressive thresholds for active health probes (respond to outright process crashes quickly). This prevents a brief global metric spike from triggering passive ejection while still rapidly ejecting truly dead hosts.

**Cost:** More configuration complexity.

**How it backfires:** A global dependency failure that lasts longer than the passive ejection window still triggers the cascade. The window buys time but doesn't prevent the failure mode.

## Interactions

- [Algorithms Under Stress](algorithms-under-stress.md) — P2C samples must be drawn from the healthy (non-ejected) pool.
- [Goodput Collapse](../overload/goodput-collapse.md) — over-ejection leaves remaining hosts with higher load, potentially driving them into collapse.
- [Correlated Failure](../dependencies/correlated-failure.md) — a global event that triggers simultaneous ejection across all backends is a correlated failure; health checking cascades are one manifestation.

## References

- Envoy Proxy documentation. "Outlier Detection." https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/outlier
  The authoritative reference for the ejection percentage cap, panic mode, and consecutive error count algorithms.
- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 22 covers health checking, oscillating failure modes, and hysteresis requirements.
