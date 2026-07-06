# Scale-Up Lag

> **One-liner:** Autoscaling responds to load increases with a delay measured in minutes — the spike shape and the lag duration together determine whether new capacity arrives before or after the damage is done.

## Symptom

- Traffic spike; service degrades; new instances appear minutes later — too late for the spike's peak.
- Degradation clears as new capacity becomes available; the damage window equals the lag duration.
- Autoscaler logs show correct decisions made quickly, but provisioning and warmup take most of the lag time.
- Inference services: scale-up lag extends to 10+ minutes due to model weight loading.

## Mechanism

Scale-up lag has three components that add in series:

**1. Detection lag (30s–5min):** Time from load increase to autoscaler deciding to scale. Driven by:
- Metric evaluation period (CloudWatch default: 5 minutes; Kubernetes HPA default: 15 seconds).
- Cooldown periods that prevent scale-out within N seconds of a previous scale event.
- Wrong signal (see [Autoscaling Signals](autoscaling-signals.md)) that doesn't register the overload.
- Threshold hysteresis: requiring the metric to be elevated for K consecutive periods before acting.

**2. Provisioning lag (30s–5min):** Time to launch a new instance and pass health checks. Driven by:
- VM or container image pull time (container image size).
- OS boot time.
- Application startup time (JVM initialization, library loading).
- Health check pass time (must pass N consecutive checks).

**3. Warmup lag (30s–30min):** Time for the new instance to reach full performance. Driven by:
- JIT compilation warmup (JVM, V8): 5–60 seconds.
- Connection pool fill: seconds to minutes depending on connection setup cost.
- Local cache warmup: minutes for a service with high cache hit rate.
- Model weight loading (inference): 5–30 minutes for large models. See [Inference Cold Starts](../inference/inference-cold-starts.md).

**Total lag for common deployments:**

| Deployment type | Typical total lag |
|----------------|-----------------|
| Kubernetes pod (pre-pulled image) | 1–3 minutes |
| Container with cold image pull | 2–5 minutes |
| VM autoscaling | 3–8 minutes |
| Serverless function (warm) | < 1 second |
| Serverless function (cold) | 1–10 seconds |
| Inference (large model) | 10–30 minutes |

**The spike-lag interaction:** Whether new capacity arrives in time depends on the spike's duration relative to the lag. A spike that lasts 10 minutes with 5-minute lag: capacity arrives halfway through; first 5 minutes are degraded. A spike that lasts 5 minutes with 5-minute lag: capacity never helps; the spike is over when instances come online.

**The sawtooth instability:** If detection lag is long and traffic is spiky, the autoscaler may oscillate: scale up to handle the spike, then scale down during the lull, then scale up again for the next spike. Each scale-up cycle incurs cold start cost; scale-down cycles remove capacity that is still warm. See [Scale-Down Safety](scale-down-safety.md).

## Real-world sightings

**Vaquero et al., "Wasted Cycles? On the Efficiency of Cloud Autoscaling" (2015).** The study measured autoscaling lag across cloud providers and found median provisioning lag of 50–120 seconds for container-based workloads, with warmup lag extending total scale-up lag to 3–5 minutes for JVM services. The paper concludes that for traffic spikes shorter than 5 minutes, autoscaling provides limited protection without pre-provisioned headroom.

**AWS Lambda "cold start" documentation.** AWS explicitly documents that Lambda cold starts add 100ms–10s of latency depending on runtime and memory size. For inference workloads using SageMaker, AWS documentation notes that model loading time is the dominant scale-up lag component, recommending minimum instance counts to avoid cold starts for latency-sensitive inference.

## Mitigations

### Predictive scaling (scheduled or ML-based)

**What it is:** Scale before the load arrives based on historical traffic patterns (scheduled scale-out before business hours, before known traffic events) or ML-based prediction of future load from leading indicators.

**Cost:** Requires stable load patterns; may overprovision during periods where the prediction is wrong. Needs organizational discipline to maintain scheduling rules.

**How it backfires:** Unexpected load spikes (product launches, viral content, incidents on another service causing traffic redirection) don't follow historical patterns. Predictive scaling helps for regular patterns, not for anomalies.

### Headroom provisioning (target utilization < 100%)

**What it is:** Configure autoscaling to target 60–70% utilization rather than 80–90%. The headroom absorbs load spikes without triggering scale-out at all — no lag if the spike fits within the headroom.

**Cost:** Permanent overprovisioning: running at 65% utilization when you could run at 85% wastes ~25% of capacity cost.

**How it backfires:** If the spike exceeds the headroom (say, 50% traffic increase at 65% baseline → 97% utilization before scale-out fires), the same lag problem recurs. Headroom only eliminates lag for spikes smaller than the headroom fraction.

### Minimum fleet size to absorb cold-start delay

**What it is:** Maintain a minimum fleet size that can handle anticipated traffic peaks without scale-out, or at least handle the traffic during the scale-up lag window at degraded but non-failing capacity.

**Cost:** Floor on the minimum fleet adds fixed capacity cost.

**How it backfires:** For inference services with 15-minute lag, the minimum fleet must handle the full expected peak — which may require a large standing fleet even at low utilization.

## Interactions

- [Autoscaling Signals](autoscaling-signals.md) — wrong signals add detection lag on top of provisioning and warmup lag.
- [Cold Starts](cold-starts.md) — warmup lag is the cold start cost of each new instance.
- [Inference Cold Starts](../inference/inference-cold-starts.md) — inference weight loading dominates scale-up lag for large models.
- [Goodput Collapse](../overload/goodput-collapse.md) — during the lag window, the service operates above its capacity ceiling; goodput collapse risk is highest here.

## References

- Vaquero, L.M. et al. "Wasted Cycles? On the Efficiency of Cloud Autoscaling." *IEEE IC2E 2015*.
  Empirical measurement of autoscaling lag across cloud providers.
- Amazon Web Services. "AWS Lambda cold starts." *AWS Documentation*.
  Official documentation on Lambda cold start latency and mitigation options.
