# Inference Cold Starts

> **One-liner:** Loading a 70B model onto GPU takes 2–10 minutes — autoscaling that responds in minutes means new capacity arrives after the surge has already caused failures, and the gap is filled only by the remaining warm instances.

## Symptom

- Traffic spike; autoscaler adds new GPU instances; failures and high TTFT persist for 3–10 minutes after scale-out decision.
- New instances visible in the orchestration dashboard but serving zero traffic (weight loading in progress).
- Health checks passing only after a significant delay (weight load + CUDA warmup complete).
- During the cold period, surviving warm instances are overloaded; KV pressure and preemption rates rise.

## Mechanism

**Inference cold start phases:**

Unlike a web service cold start (seconds), an inference cold start has five sequential phases:

**1. VM/container provisioning (30s–2min):**
The cloud provider provisions a GPU instance: allocating a physical host, booting the OS, pulling the container image. GPU instances (A100, H100) are in shorter supply than CPU instances and may have longer provisioning queues.

**2. Model weight download (30s–10min):**
Model weights must be fetched from object storage (S3, GCS, etc.) to local storage on the new instance. A 70B parameter model at bf16 = 140 GB. At 1 GB/s S3 download bandwidth: 140 seconds. With optimized model loaders and co-located storage (e.g., NFS or EFS): 30–60 seconds.

**3. Weight loading to GPU HBM (5–30s):**
Weights are transferred from CPU DRAM or NVMe to GPU HBM over PCIe. At PCIe 4.0 × 16 bandwidth (~32 GB/s): 140 GB ÷ 32 = 4.4 seconds for weights alone. Additional time for tensor format conversion, quantization, and memory mapping.

**4. CUDA kernel compilation and warmup (30s–3min):**
PyTorch, TensorFlow, and inference frameworks compile CUDA kernels on first use (just-in-time compilation). Kernels for attention, matrix multiply, and sampling are compiled on first invocation. Some frameworks use `cudaGraph` capture to record and replay static computation graphs, which requires running several warmup batches.

**5. First-batch calibration (10s–60s):**
Quantized models may require calibration on the new instance to select optimal quantization scales. Inference servers with KV cache pre-allocation need to run a first batch to establish memory layout.

**Total cold start time:**

| Model size | Typical total cold start |
|-----------|------------------------|
| 7B parameters | 2–4 minutes |
| 13B parameters | 3–6 minutes |
| 70B parameters | 5–12 minutes |
| 405B (multi-node) | 10–30 minutes |

For comparison: typical web service cold start = 15–90 seconds. Inference cold start is 5–20× longer.

**The autoscaling gap:**

A traffic spike that triggers autoscaling fires a scale-out decision (detection lag ~30–60s) and then waits for the cold start to complete (3–10 minutes). Total lag to useful new capacity: 4–11 minutes. Traffic spikes shorter than this gap receive no scaling benefit; spikes longer than this gap are served by warm instances at reduced capacity during the gap.

The surviving warm instances experience higher KV pressure (fewer hosts serving the same load), more preemptions, and higher TTFT for all users — amplifying the impact of the surge.

## Real-world sightings

**AWS SageMaker inference documentation.** AWS explicitly documents that SageMaker real-time inference endpoints have "model loading time" during scaling, which for large models can be 5–15 minutes. AWS recommends setting a minimum instance count of ≥1 and enabling "Inference Component" mode to pre-load models on standby capacity.

**Anyscale (Ray Serve) blog post on LLM serving cold starts (2023).** Anyscale published benchmark data showing that a Llama-2-70B model on an A100 instance takes approximately 4–6 minutes from autoscale trigger to first served request. The post recommends pre-warming idle instances and using speculative scaling (triggering scale-out before the threshold is breached).

## Mitigations

### Pre-provisioned standby pool

**What it is:** Maintain a minimum number of warm GPU instances that have already loaded model weights and passed warmup. The standby pool absorbs traffic surges instantly; autoscaling adds additional capacity in the background while the standby pool handles the surge.

**Cost:** Standby GPU instances idle at near-zero utilization. GPU instance costs are high (A100 ≈ $3–$5/hour at list price on cloud providers). A pool of 2 standby A100 instances = $6–$10/hour of idle cost.

**How it backfires:** The standby pool is sized for an expected surge magnitude. A larger-than-expected surge exhausts the standby pool before new cold-start instances are ready, leaving the same gap problem but shifted to a higher load level.

### Fast weight loading from local NVMe snapshot

**What it is:** On instance initialization, instead of downloading model weights from remote object storage, load from a local NVMe snapshot that was pre-populated (e.g., via a custom AMI/image that includes the weights, or via an NVMe initialization script that runs once per physical host). This eliminates the S3 download step (the largest contributor to cold start time).

**Cost:** Custom machine images are model-specific; a new model version requires a new image. Storage cost for per-host weight snapshots. Cloud provider support for custom AMIs with GPU drivers varies.

**How it backfires:** If the instance is provisioned on a new physical host that doesn't have the NVMe snapshot, the fast path falls back to object storage download. NVMe snapshot freshness must be managed when model weights are updated.

### Predictive scaling with load forecasting

**What it is:** Scale out *before* the expected surge based on traffic forecasting. For predictable load patterns (business hours, daily peaks, scheduled events), trigger scale-out 15–30 minutes before the expected ramp to ensure capacity is warm when needed.

**Cost:** May overprovision during periods where the forecast is wrong. Requires a traffic forecasting system with sufficient accuracy.

**How it backfires:** Unexpected surges (viral content, product launches, incidents redirecting traffic) don't follow historical patterns. Predictive scaling helps for regular patterns; unpredictable spikes still hit the cold start gap.

## Interactions

- [Scale-Up Lag](../capacity/scale-up-lag.md) — inference cold start is the dominant component of scale-up lag for GPU-based inference; the warmup lag component alone exceeds typical web service total lag.
- [Cold Starts](../capacity/cold-starts.md) — the classical cold start problem (JIT, connection pools) applies within the inference server too, on top of the weight loading cost.
- [KV Cache Pressure](kv-cache-pressure.md) — during the cold start gap, remaining warm instances serve more traffic at higher KV occupancy; preemption rates rise.
- [Autoscaling Signals](../capacity/autoscaling-signals.md) — KV cache occupancy is the correct autoscaling signal for inference; CPU utilization does not capture GPU memory pressure.
- [Static Stability](../capacity/static-stability.md) — the inference serving fleet's data plane must continue serving at current capacity during autoscaler control plane failures; cold start lag amplifies the impact of such failures.

## References

- Amazon Web Services. "SageMaker real-time inference: model loading time." *AWS Documentation*.
  Documents inference model loading latency and recommends minimum instance count for latency-sensitive endpoints.
- Kwon, W. et al. "Efficient Memory Management for Large Language Model Serving with PagedAttention." *SOSP 2023*.
  Section 5 describes the vLLM deployment setup, including weight loading optimization and GPU warmup steps.
