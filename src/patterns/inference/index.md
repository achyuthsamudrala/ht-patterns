# Inference

Inference serving violates several classical distributed systems assumptions:

- **Unknown work size:** output length is not known at admission time.
- **State is not free:** the KV cache that accelerates decoding consumes GPU memory proportional to sequence length × active requests.
- **Two-phase execution:** prefill (prompt processing) and decode (token generation) have different compute profiles and different SLOs.
- **Cold starts are in minutes:** loading model weights takes 1–10 minutes on typical hardware.

These properties make patterns from other sections apply differently — or not at all.

## Patterns in this section

- [Unknown Work Size](unknown-work-size.md)
- [Continuous Batching](continuous-batching.md)
- [KV Cache Pressure](kv-cache-pressure.md)
- [Prefill vs. Decode](prefill-vs-decode.md)
- [Token-Level SLOs](token-level-slos.md)
- [Prefix Caching](prefix-caching.md)
- [Priority and Preemption](priority-and-preemption.md)
- [Inference Cold Starts](inference-cold-starts.md)
