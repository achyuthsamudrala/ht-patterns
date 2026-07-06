# Scale-Down Safety

> **One-liner:** Removing an instance while it serves live requests drops those requests — and premature scale-down during a load lull means the next uptick hits reduced capacity without warmup.

## Symptom

- Periodic error spikes at regular intervals that correlate with autoscaler evaluation cycles.
- Error rate increases precisely when instance count decreases; recovers as the fleet stabilizes.
- Errors are connection resets or abrupt closes rather than application-level errors — the server is disappearing mid-connection.
- After a traffic lull, latency spikes when traffic returns — new instances are serving cold traffic.

## Mechanism

**The in-flight request problem:**

When an instance is removed from the pool immediately (SIGKILL or load balancer deregistration without drain), in-flight requests on that instance fail. The failure mode depends on the protocol:
- HTTP/1.1: connection reset; client receives a 5xx or a connection error.
- HTTP/2 / gRPC: RST_STREAM on all active streams.
- TCP: connection closed mid-response.

The correct procedure — connection draining — removes the instance from the LB pool first, waits for in-flight work to complete, then terminates. This requires:
1. LB removes the instance from the routing pool (new requests stop arriving).
2. The instance finishes all in-flight requests.
3. The instance acknowledges drain complete (or a drain timeout fires).
4. The instance is terminated.

**Drain timeout:** Long-running requests (exports, analytics queries, streaming responses) can hold draining open indefinitely. A maximum drain timeout (30–120 seconds) prevents infinite drain; requests still active at the timeout are dropped. Setting the right timeout requires knowing the p99 of long-tail request durations.

**The oscillation problem:**

Autoscalers use cooldown periods to prevent thrashing — scaling down, then up, then down. If the cooldown is too short relative to the traffic pattern period (e.g., 5-minute cooldown on a 10-minute demand cycle), the autoscaler oscillates:

1. Traffic high → scale up to 10 instances.
2. Traffic drops → autoscaler scales down to 6 instances.
3. Traffic rises again → scale up to 10 instances.
4. Each scale-up pays cold start cost; each scale-down drops in-flight requests.

The sawtooth pattern is visible in instance count and latency time series. The fix: longer cooldowns, more aggressive scale-down thresholds (require sustained low load before scaling down), or minimum floor on instance count.

**The premature scale-down trap:**

An autoscaler that scales down aggressively during a brief lull removes warm instances with warm caches, warm JIT, warm connection pools. When traffic returns, the smaller fleet handles it with cold instances. The scale-up response incurs the full cold start cost at exactly the moment when capacity is needed.

## Real-world sightings

**Kubernetes connection draining behavior.** Kubernetes implements graceful termination via `terminationGracePeriodSeconds`: when a pod is terminated, it receives SIGTERM and has `terminationGracePeriodSeconds` (default: 30s) to finish in-flight work before SIGKILL. Services must handle SIGTERM by stopping new request acceptance while finishing current work. A common mistake: services that don't implement SIGTERM handling are killed immediately, dropping requests.

**AWS Auto Scaling lifecycle hooks.** AWS Auto Scaling provides lifecycle hooks that allow custom actions during scale-in events. A lifecycle hook fires when an instance is selected for termination, pausing the termination until the hook completes. This is the mechanism for implementing connection draining outside of load balancer drain: the hook allows the instance to complete in-flight work before the autoscaler proceeds with termination.

## Mitigations

### Connection draining with bounded timeout

**What it is:** Before terminating an instance, signal the load balancer to stop routing new requests to it (deregister or set weight to zero). Wait for in-flight request count to reach zero (or for a maximum drain timeout to fire). Then terminate.

**Cost:** Instances take longer to remove (drain time adds to scale-down latency). Requires LB integration.

**How it backfires:** Hung or very long-running requests can keep the instance in drain indefinitely. Set a maximum drain timeout matched to the p99 of long-tail request durations; accept that requests beyond the timeout are dropped.

### Scale-down cooldown and hysteresis

**What it is:** Require sustained low utilization before scaling down. Use a longer cooldown period after scale-down events than after scale-up events. Scale down by smaller increments (remove 1–2 instances at a time, not 50% of the fleet) to limit blast radius.

**Cost:** Slower scale-down increases idle capacity cost during genuine load reduction.

**How it backfires:** A cooldown that's too long prevents scale-down during a sustained genuine load reduction, maintaining unnecessary capacity for hours.

### Minimum instance floor

**What it is:** Set a minimum instance count that is never scaled below. The floor is sized to handle anticipated traffic during the scale-up lag window without degrading. Below the floor, scale-down does not fire regardless of utilization.

**Cost:** Permanent minimum capacity cost; floor must be revisited as baseline traffic changes.

**How it backfires:** A floor set for current traffic patterns may be too low if traffic grows significantly, or too high (wasteful) if traffic decreases over time.

## Interactions

- [Cold Starts](cold-starts.md) — premature scale-down followed by scale-up cycles through cold start cost at the worst moment.
- [Scale-Up Lag](scale-up-lag.md) — scale-down and subsequent scale-up incur the full lag; a conservative scale-down policy reduces unnecessary lag cycles.
- [Health Checking](../load-balancing/health-checking.md) — draining is implemented via health check manipulation; a draining instance should fail health checks to stop receiving new traffic.

## References

- Kubernetes documentation. "Pods: Termination of Pods." https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/
  Describes the SIGTERM → graceful termination → SIGKILL sequence and `terminationGracePeriodSeconds`.
- Amazon Web Services. "Auto Scaling lifecycle hooks." *AWS Documentation*.
  Describes how lifecycle hooks enable custom drain logic during scale-in events.
