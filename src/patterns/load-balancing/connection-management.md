# Connection Management

> **One-liner:** Connection setup is expensive; when every client simultaneously establishes connections to a new backend, the connection storm saturates it before it serves a single request.

## Symptom

- Latency spike immediately after adding a new backend to the pool — before it processes any application-level requests.
- TCP connection errors and TLS handshake failures on the new backend at startup.
- Timeout errors visible at the client without corresponding application errors at the server — connection setup is timing out.
- HTTP/2 or gRPC traffic appearing to load-balance unevenly — all traffic from one proxy to one backend because only one connection exists.
- Connection pool exhaustion during traffic spikes: requests queue waiting for a pool slot rather than a server thread.

## Mechanism

**Connection setup cost:**

A single new connection involves:
1. TCP 3-way handshake: ~0.5 × RTT (1ms on local network, 50ms cross-region).
2. TLS handshake: 1–2 RTTs + CPU for key exchange and certificate verification.
3. Application-level authentication: 1–3 RTTs depending on auth protocol.
4. Connection pool initialization: additional state setup per pool implementation.

Total cost: 5–200ms depending on RTT and auth depth. This is 5–200× the cost of reusing an existing connection for a 1ms request.

**Connection storms:**

When a new backend is added to the pool (scale-out, deploy, recovery), every load balancer, proxy, and client that routes to that backend attempts to establish connections simultaneously. A backend with 50 load balancer instances, each establishing 10 connections, receives 500 simultaneous connection requests before serving any application traffic. The backend's accept queue fills; TLS CPU spikes; latency for the new connections climbs — potentially causing health check failures before the backend is ready to serve.

**Pool exhaustion dynamics:**

A connection pool has a maximum size N. Under steady-state load, N is sized for average concurrency. Under a traffic spike, concurrency exceeds N: new requests wait in a queue for a connection to free. If the queue wait exceeds the request SLO, requests time out from the queue rather than from the application.

The pool exhaustion timeline:
1. Traffic spike arrives.
2. Concurrency = RPS × mean_latency (by Little's Law) exceeds pool size N.
3. Requests queue for connections. Queue depth = excess concurrency.
4. Queue wait increases effective request latency.
5. Requests exceed timeout from queue wait → errors.
6. Clients retry (see [Retry Storms](../overload/retry-storms.md)) → more requests queuing.

**HTTP/2 multiplexing and load balancing mismatch:**

HTTP/2 multiplexes multiple requests over a single TCP connection. This is efficient (no per-request connection cost), but creates a load balancing problem: if the load balancer or proxy has only one connection per backend, all traffic between a client-proxy pair goes to one backend on that connection. Round-robin and P2C operate at the request level, but if connections aren't distributed, request-level routing is ineffective.

Envoy, NGINX, and Linkerd address this by maintaining multiple connections per backend (controlled by `max_connections_per_endpoint` or equivalent). gRPC load balancing (either at the proxy or client level) must explicitly manage connection counts to achieve per-request distribution.

## Real-world sightings

**AWS Lambda and container cold starts.** AWS documentation describes the "thundering herd" on new Lambda function instances or new container registrations: all concurrent invocations attempt to establish connections to the new instance simultaneously, causing a burst of TLS setup that saturates the new instance's CPU before it starts processing requests. AWS recommends using a gradual warm-up strategy or provisioned concurrency to pre-establish connections.

**Envoy connection pool documentation.** Envoy's HTTP connection pool documentation explains that for HTTP/1.1, Envoy maintains a pool of N connections and queues requests when the pool is full. For HTTP/2, Envoy maintains fewer connections (since they multiplex) but must track per-connection stream counts to ensure streams are distributed across connections to multiple backends.

## Mitigations

### Pre-establishing connections before traffic routing

**What it is:** When a new backend is added to the pool, establish the minimum pool connections *before* directing traffic to the backend. Health checks pass only after the connection pool is pre-warmed. Traffic is then routed to a backend that already has live, authenticated connections.

**Cost:** Adds latency to backend registration. Requires the connection pool implementation to support pre-warming.

**How it backfires:** Pre-warming establishes minimum-pool connections. Under a traffic spike that exceeds pool size, establishment of additional connections still races.

### Gradual connection establishment via slow-start

**What it is:** When adding a new backend, ramp its routing weight from low to full over a connection establishment window. The low initial weight ensures only a small fraction of clients establish connections at once, rather than all simultaneously.

**Cost:** New capacity is not fully available immediately; adds time to scale-out operations.

**How it backfires:** Under an urgent traffic spike requiring fast scale-out, slow connection ramping delays capacity availability. The ramp period must be tuneable and bypassable.

### Connection pool sizing by Little's Law

**What it is:** Size the connection pool based on peak expected concurrency: N ≥ RPS_peak × mean_latency. Review pool size when either traffic patterns or backend latency changes.

**Cost:** Larger pools consume resources on both client and server (file descriptors, kernel TCP state, TLS state).

**How it backfires:** Pool sized for peak is oversized during normal load, consuming unnecessary resources on the server. If the backend enforces a max connection limit, a too-large pool may hit the backend's limit before pool exhaustion is a problem on the client side.

### HTTP/2 connection count tuning

**What it is:** For gRPC or HTTP/2 backends, configure the proxy or client to maintain multiple connections per backend (e.g., `max_connections = max(1, target_rps / max_concurrent_streams)`). This ensures request-level load balancing is effective — multiple connections distribute requests across shards of the backend.

**Cost:** More connections per backend increase file descriptors and kernel state.

**How it backfires:** Too many connections per backend can overwhelm the backend's connection table. Each multiplexed connection also creates head-of-line blocking at the TCP stream level; more connections reduce HOL blocking risk.

## Interactions

- [Algorithms Under Stress](algorithms-under-stress.md) — load balancing algorithms (P2C, EWMA) operate at the request level, but effectiveness depends on having adequate connections to each backend.
- [Cold Restart Warmup](../caching/cold-restart-warmup.md) — connection storms are a component of cold restart cost; page faults and connection setup together cause the startup latency spike.
- [Retry Storms](../overload/retry-storms.md) — connection pool exhaustion drives request errors; retries compound the exhaustion.

## References

- Amazon Web Services. "Connection management for Lambda." *AWS Documentation*.
  Describes connection storm behavior for Lambda and container-based scaling; recommends pre-warming.
- Envoy Proxy documentation. "Connection Pools." https://www.envoyproxy.io/docs/envoy/latest/intro/arch_overview/upstream/connection_pooling
  The canonical reference for HTTP/1.1 and HTTP/2 connection pool behavior in a production proxy.
- Grigorik, I. *High Performance Browser Networking*. O'Reilly, 2013.
  Chapters 2–4 cover TCP, TLS, and HTTP/2 connection setup costs in detail; the numbers in this page derive from this analysis.
