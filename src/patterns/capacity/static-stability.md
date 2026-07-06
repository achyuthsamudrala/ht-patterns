# Static Stability

> **One-liner:** A service that requires its control plane to function during a crisis will fail at exactly the moment the control plane is also under stress — data planes must be able to operate on stale-but-sufficient configuration.

## Symptom

- Control plane (autoscaler, config service, service registry, certificate authority) degraded or partitioned.
- Data plane (the actual service) misbehaves in response: stops serving, loops on failed initialization, or rejects requests because it can't refresh its config.
- Incident where fixing the control plane restores the data plane, confirming the dependency.
- Service fails to restart after a deploy because the config service it bootstraps from is temporarily unavailable.

## Mechanism

**The control plane / data plane coupling:**

Modern distributed systems separate the *control plane* (components that configure, discover, and manage the data plane) from the *data plane* (components that process user requests). Examples:

| Control plane | Data plane |
|--------------|-----------|
| Service registry (Consul, ZooKeeper) | Application servers |
| Config service (etcd, AWS AppConfig) | Feature flag-driven services |
| Certificate authority | TLS-terminating services |
| Autoscaler (HPA, ASG) | Worker instances |
| Load balancer control plane | Load balancer data plane |

**Static stability** is the property that the data plane continues to operate correctly in the absence of the control plane, using its last-known-good state. The alternative — *dynamic dependency* on the control plane — means control plane failures immediately propagate to the data plane.

**Why control plane outages happen at the worst time:** Control planes are often stressed during the same events that stress data planes — a major traffic spike triggers autoscaling decisions, config changes, and service discovery updates simultaneously. A traffic spike that causes the autoscaler to try to launch many instances may overwhelm the service registry or container orchestrator. The control plane failure amplifies the data plane stress.

**Failure modes from dynamic coupling:**

*Startup dependency:* Service fails to start if the config service is unavailable during initialization. A rolling deploy during a config service outage fails all new instances. The fix: cache the config locally on the first successful fetch; use it if the config service is unavailable on restart.

*Certificate renewal:* TLS certificates have expiry dates. A service that cannot renew certificates because the CA is unavailable will eventually serve expired certificates (or refuse connections, depending on configuration). The fix: renew early; cache and serve the certificate regardless of whether renewal is currently possible.

*Service discovery:* A service that re-resolves its dependencies on every request is vulnerable to service registry outages. The fix: cache the resolved endpoint list; use the cache if the registry is unavailable; only update when a successful resolution occurs.

## Real-world sightings

**Amazon Web Services, "Static stability using Availability Zones."** The Builders' Library essay describes the principle as "the data plane should not require the control plane in order to function during steady-state operations." The essay gives a concrete example: EC2 instances in an Auto Scaling group should continue running during an Auto Scaling API outage; the instances don't need the autoscaler to serve traffic — they need it only for scaling events.

**HashiCorp Consul gossip protocol.** Consul's data plane (service health information) is distributed via gossip protocol, allowing agents to continue reporting service health and routing traffic even when the Consul server cluster is partitioned. Agents cache the last-known service catalog and serve from cache during server partitions, embodying static stability.

## Mitigations

### Last-known-good configuration caching

**What it is:** Cache configuration locally (in-process or on disk) after each successful fetch from the config service. If the config service is unavailable, use the cached version. Set a maximum staleness window; if the cache is older than the window, decide whether to fail safe (use stale) or fail open (refuse to serve).

**Cost:** Stale configuration during control plane outage. If the reason for the control plane outage is a bad config push, the stale config may be the last good one — which is usually correct behavior.

**How it backfires:** If a config change is security-critical (rotating a compromised credential), the inability to apply it because the control plane is down is a safety concern. Distinguish between "optional" and "security-critical" configuration; handle each differently.

### Startup independence from the control plane

**What it is:** Services should not block startup on config service availability. Bootstrap with a local config file or environment variables; attempt to fetch the latest config asynchronously; apply it if available, but serve with defaults if not.

**Cost:** Adds a "bootstrap config" path that may differ from the "runtime config" path; both must be correct.

**How it backfires:** A service that starts with stale or default config may behave differently from expected (e.g., feature flags in wrong state) until the fresh config is fetched. Operators must know this is expected during config service outages.

### Control plane fallback paths

**What it is:** Design the control plane itself with static stability — if the primary control plane is unavailable, fall back to a simpler mechanism. Example: if the service registry is down, fall back to DNS-based discovery. If the feature flag service is down, fall back to compile-time defaults.

**Cost:** Requires maintaining multiple discovery/configuration paths; adds complexity.

**How it backfires:** Fallback paths that are rarely exercised develop bugs. Test fallback paths explicitly in chaos engineering exercises.

## Interactions

- [Correlated Failure](../dependencies/correlated-failure.md) — control plane and data plane failing together is correlated failure; static stability prevents the correlation.
- [Autoscaling Signals](autoscaling-signals.md) — the autoscaler is a control plane component; data plane must continue at current capacity during autoscaler outage.
- [Scale-Up Lag](scale-up-lag.md) — during a control plane outage, scaling is impossible; the existing fleet must absorb the load.

## References

- Amazon Web Services. "Static stability using Availability Zones." *AWS Builders' Library*.
  The canonical description of the pattern; the AZ-level example is clear and directly applicable.
- Kleppmann, M. *Designing Data-Intensive Applications*. O'Reilly, 2017.
  Chapter 9 discusses the CAP theorem in the context of the availability/consistency tradeoff; static stability is an application of choosing availability.
