# Autoscaling Signals

> **One-liner:** Autoscaling on the wrong metric means no scale-up during the brownout that makes the correct metric spike — CPU looks fine while every thread is blocked waiting on a slow dependency.

## Symptom

- Service degraded (high latency, elevated error rate); autoscaler not adding capacity.
- The metric driving autoscaling (typically CPU %) looks normal while the service is saturated.
- Queue depth or in-flight request count rising without triggering scale-out.
- Scaling eventually fires, but only after degradation is already severe and self-correcting.

## Mechanism

**Why CPU is the wrong signal for IO-bound services:**

CPU utilization autoscaling works when the bottleneck *is* the CPU. In compute-bound services (image resizing, video encoding, cryptography), CPU ≈ load. When the CPU is at 80%, the service is at 80% capacity.

For IO-bound services (web applications making database and cache calls, microservices calling other microservices), threads spend most of their time blocked waiting on I/O. CPU can be at 10% while all 200 threads are blocked waiting on a slow database. From the autoscaler's perspective, CPU is low, no scale-out is needed. From the user's perspective, every request is queued waiting for a thread.

**The bottleneck determines the signal:**

| Service type | Bottleneck | Correct signal |
|-------------|-----------|----------------|
| Compute-bound | CPU cores | CPU % |
| Thread-per-request IO-bound | Thread pool | Thread pool utilization or queue depth |
| Event-loop IO-bound | In-flight count | Pending callbacks or connection count |
| Database-backed | DB connections | Connection pool exhaustion or DB latency |
| Inference (GPU) | GPU memory / KV cache | KV cache occupancy, batch queue depth |

**The CPU-as-signal failure mode:** An IO-bound service at 200 RPS with 200 threads and 1-second dependency timeouts:
- Each thread is blocked for ~1 second.
- By Little's Law: 200 RPS × 1s = 200 in-flight ≈ the thread pool limit.
- CPU: 10% (threads are sleeping, not executing).
- Autoscaler: "low CPU, no action needed."
- Reality: all threads blocked; new requests queuing; p99 ≫ SLO.

**Lag compounds the wrong-signal problem:** Even with the right signal, autoscaling has detection lag, provisioning lag, and warmup lag (see [Scale-Up Lag](scale-up-lag.md)). A wrong signal adds additional detection lag on top. By the time a CPU-based autoscaler detects that the thread-blocked IO service is degraded, the signal has to propagate through: (1) blocking threads cause errors, (2) errors cause clients to retry, (3) retries increase load, (4) load eventually increases CPU. This path takes minutes.

**Inference-specific signals:** GPU memory occupancy and KV cache hit rate are better autoscaling signals than GPU utilization for inference workloads. A GPU can be at 30% utilization (compute) while KV cache is at 95% (memory), meaning new requests will be rejected or will evict existing ones. See [KV Cache Pressure](../inference/kv-cache-pressure.md).

## Real-world sightings

**Amazon Web Services, "Implementing health checks."** The Builders' Library essay notes that CPU utilization is unreliable as an autoscaling signal for services with blocking I/O. The recommendation is to expose a custom metric that reflects actual work capacity — typically thread pool utilization or request queue depth — and scale on that metric rather than CPU.

**Google SRE Book (Beyer et al., 2016).** Chapter 17 covers autoscaling and discusses signal selection. The book recommends scaling on latency or error rate (downstream SLO signal) rather than resource utilization (upstream capacity signal), arguing that user-visible degradation is the metric that matters.

## Mitigations

### Queue depth or concurrency-based scaling

**What it is:** Export a metric that measures the actual bottleneck: thread pool utilization (threads_in_use / threads_total), queue depth (requests waiting for a worker), or in-flight request count. Autoscale when this metric exceeds a threshold.

**Cost:** Requires custom metric export; threshold is service-specific and must be tuned.

**How it backfires:** Queue depth can spike briefly during load bursts without indicating sustained overload. Scale-out must be debounced (require the metric to be elevated for N consecutive evaluation periods) to avoid thrashing.

### Custom saturation metrics

**What it is:** Instrument the specific bottleneck resource. For a database-backed service: connection pool wait time. For an inference service: KV cache occupancy. For a thread-per-request service: thread pool exhaustion rate. Export as a custom CloudWatch, Prometheus, or Datadog metric; configure autoscaling to react to it.

**Cost:** Instrumentation work per service; alert thresholds must be revisited as the service evolves.

**How it backfires:** A metric that measures the bottleneck correctly during normal operation may not correctly measure it during a novel failure mode. A service that develops a new bottleneck (say, disk I/O) still autoscales on the old bottleneck (thread pool) and misses the new constraint.

### SLO-based autoscaling (latency or error rate)

**What it is:** Scale when p99 latency exceeds threshold or error rate exceeds threshold — the downstream user-visible signal rather than the upstream resource signal.

**Cost:** Lags the actual bottleneck; by the time p99 spikes, damage is already occurring. Also harder to set thresholds that don't false-fire during transients.

**How it backfires:** p99 latency SLO-based autoscaling is reactive by definition — it scales after users are already affected. Requires tight thresholds and fast provisioning to minimize the degradation window.

## Interactions

- [Scale-Up Lag](scale-up-lag.md) — even with the right signal, new capacity takes minutes to arrive.
- [Goodput Collapse](../overload/goodput-collapse.md) — wrong autoscaling signal means no scale-up during collapse, prolonging it.
- [KV Cache Pressure](../inference/kv-cache-pressure.md) — inference autoscaling on GPU memory rather than GPU utilization.

## References

- Beyer, B. et al. *Site Reliability Engineering*. O'Reilly, 2016.
  Chapter 17 covers autoscaling signal selection and the argument for latency-based over CPU-based signals.
- Amazon Web Services. "Implementing health checks." *AWS Builders' Library*.
  Discusses custom metrics and why CPU is an unreliable signal for IO-bound services.
- Brendan Gregg. *Systems Performance*. Prentice Hall, 2013.
  Chapter 2 covers saturation metrics: the USE method (Utilization, Saturation, Errors) provides a framework for choosing the right autoscaling signal per resource type.
