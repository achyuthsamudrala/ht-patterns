# Deadline Propagation

> **One-liner:** Without propagating the original request's deadline through every downstream hop, subtasks continue executing after the client has already given up — consuming capacity for output that will never be delivered.

## Symptom

- High CPU on downstream services even after upstream timeout fires; traces show subtasks completing after the root request has already returned an error.
- Request traces with deep fanout show many completed subtasks but the root request timed out before all returned.
- Server-side latency histograms look healthy at p50; client-side latency histograms show high p99 (client timed out while server was still working).
- Under overload, capacity feels lower than expected — "zombie work" consuming resources for already-failed requests.
- Removing a deadline leaves downstream services thrashing indefinitely when upstream dies.

## Mechanism

A client sets timeout T on its request. The server fans out to N downstream services, each with independent timeouts T₁, T₂, ..., Tₙ. If any Tᵢ > T, that downstream continues working after the client has already given up.

**Zombie work** is the result: processing that generates no useful output because the consumer is gone. The resource cost is real — CPU, memory, downstream connections — but the goodput contribution is zero. Under heavy load, a service whose requests have long timeouts at leaf nodes can spend the majority of its CPU on zombie work from already-failed requests.

The math is straightforward. At fan width N with N independent deadlines of length T₁ each, the fraction of work that is zombie is approximately:

> zombie_fraction ≈ max(0, (T₁ - T) / T₁) × (1 - goodput_rate)

At overload (goodput_rate = 0.5) with T₁ = 2× T: approximately 50% of the downstream service's capacity is zombie work.

**Correct deadline propagation** passes the *remaining* deadline (not the original timeout duration) to each downstream call. The remaining deadline = original_deadline - now. Each downstream hop checks on arrival: if remaining deadline ≤ 0, return immediately with an error. Otherwise, proceed and cancel its own downstream calls when its deadline expires.

This requires:
1. Clocks: absolute deadlines (not relative timeouts) propagate correctly across hosts with small clock skew. gRPC uses absolute timestamps in the deadline header.
2. Cooperative cancellation: downstream code must check for cancellation at yield points (after IO, before starting expensive work).
3. Idempotency: cancellation mid-operation must leave the system in a consistent state.

**gRPC deadlines** implement this correctly. When a gRPC call is cancelled (client disconnects or deadline passes), the server receives a cancellation signal on the context. Code that checks `ctx.Done()` can short-circuit immediately. Code that doesn't check continues executing, becoming zombie work.

**HTTP without propagation** is the common anti-pattern. Each service sets its own timeout independently. The originating service timeout is 5s; the next service downstream has a 10s timeout; the leaf service has no timeout. A slow leaf runs for minutes after the user's request has failed.

## Real-world sightings

**Google Dapper (Sigelman et al., 2010).** Google's distributed tracing system was built in part to make deadline propagation visible — to show in production traces where subtasks outlive their root request. The Dapper paper notes that propagating context through all RPC calls is a prerequisite for understanding and controlling distributed latency.

**gRPC documentation and design rationale.** gRPC's built-in deadline mechanism (grpc.Deadline) was designed specifically to solve the zombie work problem. The design notes that without deadlines, a cancelled client request can cause downstream services to continue processing indefinitely. The gRPC framework propagates deadlines through all hops automatically when all hops use gRPC, eliminating the need for manual propagation.

## Mitigations

### Absolute deadline propagation via metadata

**What it is:** On every outbound call, include the absolute deadline timestamp (wall clock when the request expires). The recipient checks this on arrival; if expired, returns immediately. All intermediate hops propagate the same deadline, reduced by local clock offset.

**Cost:** Requires all services in the call graph to implement deadline checking. Clock skew between hosts must be small relative to the deadline (< 100ms for a 1s deadline is fine; < 100ms for a 10ms deadline is not).

**How it backfires:** Clock skew can cause premature rejection (clocks disagree on whether the deadline has passed). A service that aggressively checks deadlines on arrival may reject requests during a network delay that wouldn't have actually expired.

### Context cancellation propagation

**What it is:** Use the runtime's context mechanism (Go's `context.Context`, Java's `Context` in gRPC) to propagate cancellation. When the root context is cancelled (timeout or caller disconnect), all downstream calls on that context receive a cancellation signal.

**Cost:** All I/O and long-running computations must check the context for cancellation. Blocking I/O may not respect cancellation (blocking syscalls are not interrupted by context cancellation in most runtimes).

**How it backfires:** Uncooperative code (tight loops, blocking IO, external library calls) ignores context cancellation and continues running. A subtask that needs to complete for data consistency reasons (a database write that has started) cannot be safely cancelled mid-operation.

### Deadline-aware queue management

**What it is:** Before a worker dequeues an item, check its deadline. Discard expired items without processing them. This is most effective combined with absolute deadline metadata on queue items.

**Cost:** Requires deadline metadata on every item; adds a check per dequeue.

**How it backfires:** Discarded items may have started downstream work (a database row partially updated). Without transactional guarantees, partial work must be explicitly cleaned up.

## Interactions

- [Fanout Amplification](../tail-latency/fanout-amplification.md) — zombie work amplifies with fan width: N fans × T_zombie each = N×T_zombie of wasted capacity.
- [Goodput Collapse](goodput-collapse.md) — zombie work reduces capacity available for live requests, compounding collapse.
- [Queue Management](queue-management.md) — deadline-aware queuing is the queue-side complement to deadline propagation.
- [Retry Storms](retry-storms.md) — retries without deadline awareness retry even when the root request's deadline has already passed.

## References

- Sigelman, B.H. et al. "Dapper, a Large-Scale Distributed Systems Tracing Infrastructure." *Google Technical Report*, 2010.
  Describes context propagation and deadline visibility as foundational requirements for distributed systems observability.
- gRPC documentation. "Deadlines." https://grpc.io/docs/guides/deadlines/
  The practical guide to gRPC deadline propagation; covers how deadlines propagate through call chains and what happens when they expire.
- Nygard, M. *Release It!* 2nd ed. Pragmatic Programmers, 2018.
  Chapter 5 covers timeouts at each layer of a distributed system; the deadline propagation pattern is derived from this treatment.
