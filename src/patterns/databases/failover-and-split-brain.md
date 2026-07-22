# Failover and Split-Brain

> **One-liner:** Promoting a replica to primary during a failure takes time and works from imperfect information; get the timing or the fencing wrong and two nodes can end up both accepting writes as "the" primary at once.

## Symptom

- Data inconsistency is discovered only *after* an incident, not during it — rows present on one node and absent on the other, or conflicting values for the same row.
- Monitoring briefly shows two nodes both reporting as primary/writable simultaneously.
- Failover completes "successfully" according to the orchestration tooling, but application-level errors or inconsistencies continue for a window afterward.
- Writes accepted during a network partition are later found to conflict with writes accepted elsewhere, or to have been silently lost.
- Every failover event is followed by a manual reconciliation or backfill job to find and resolve the divergence.

## Mechanism

Automated failover systems (Orchestrator for MySQL, Patroni for PostgreSQL, and similar replication managers) detect a primary's failure via missed heartbeats, then promote the most caught-up available replica to take its place. Three separate gaps in this process create risk:

1. **Detection lag.** The time between the primary actually failing (or becoming partitioned) and the failover system detecting it. During a *partial* network partition — the primary is unreachable from the orchestrator but still reachable by some clients — the old primary can continue accepting writes from those clients for the entire detection window.
2. **Replication lag at the moment of promotion.** Under asynchronous replication, the replica chosen for promotion may not have received the primary's most recent committed writes. Promoting it makes those writes permanently unreachable through the new topology — data loss, not just delay (see [Replication Lag](replication-lag.md)).
3. **No fencing of the old primary.** Without an explicit mechanism to guarantee the old primary can no longer accept writes, it can come back online after a transient partition heals and resume accepting writes exactly as before — now with a *second* node also accepting writes as primary. This is split-brain: the failure isn't in choosing wrong, it's in never getting the old primary to definitively stop.

Consensus-based systems (Raft, Paxos groups) sidestep the heuristic version of this problem structurally: leadership is granted by majority quorum agreement rather than by an external orchestrator's best guess, and a node that can't reach a quorum cannot act as leader, full stop. This trades single-primary async replication's lower write latency for a guarantee that no promotion decision is made on partial information — at the cost of every write requiring a quorum round-trip.

## Real-world sightings

**GitHub, "October 21 post-incident analysis" (GitHub Engineering Blog, 2018).** A network partition between GitHub's US East Coast data center facilities caused their Orchestrator-managed MySQL topology to promote a new primary in one facility while a small number of writes continued landing on the old primary in the other facility before the partition was fully resolved. The divergence required an extended manual reconciliation process and roughly 24 hours of degraded service to fully resolve — one of the most detailed public accounts of exactly how detection lag and replication lag compound during a real partition, from a company that was already running mature, widely-used failover automation.

**Corbett, J. et al., "Spanner: Google's Globally-Distributed Database" (OSDI 2012).** Spanner's design is, in large part, a direct answer to this class of problem: rather than heuristic failover for a single-primary topology, each piece of data is owned by a Paxos group that elects its own leader via quorum, and TrueTime-based timestamps let the system reason about global ordering without depending on any single node's clock or availability. The paper is worth reading specifically as the "what if we designed around this from the start" counterpoint to retrofit failover automation.

## Mitigations

### Fencing tokens

**What it is:** Issue a monotonically increasing token on every promotion; every downstream system that accepts writes checks the token and rejects any write carrying an older token than the highest it has seen.

**Cost:** Every write path — not just the database, but any downstream system a client might write to using credentials or state issued before the promotion — must actually check and enforce the token.

**How it backfires:** If a downstream system merely logs the token without enforcing it, fencing is theater: the mechanism exists, but a stale writer's requests still succeed exactly as if there were no fencing at all.

### Active fencing (STONITH) of the old primary

**What it is:** Before completing a promotion, forcibly ensure the old primary can no longer serve writes — power it off, isolate it at the network layer, or revoke its credentials — rather than merely electing a new primary and hoping the old one has stopped.

**Cost:** Adds latency to failover, since promotion must wait for confirmation that fencing succeeded, and requires reliable out-of-band infrastructure to perform the fencing.

**How it backfires:** If the fencing mechanism is unreachable during the same partition that triggered the failover in the first place, the system faces a genuine choice with no clean answer: stall promotion until fencing is confirmed (safe but unavailable), or proceed without confirmation (fast but risks exactly the split-brain fencing exists to prevent).

### Semi-synchronous replication to the promotion candidate

**What it is:** Require the replica most likely to be promoted to acknowledge each write before the primary considers it committed, bounding data loss on promotion to whatever wasn't yet acknowledged.

**Cost:** Adds commit latency to every write, proportional to the round trip to that replica.

**How it backfires:** Many semi-sync implementations fall back to asynchronous replication if the synchronous replica becomes slow or unreachable, in order to preserve primary availability — silently reopening exactly the data-loss window the mechanism was added to close, at precisely the moment (replica trouble) it matters most.

### Consensus-based replication instead of heuristic failover

**What it is:** Replace single-primary async replication with a quorum-based system (Raft/Paxos — etcd, CockroachDB, Spanner) where leadership requires majority agreement rather than an external orchestrator's decision.

**Cost:** Higher baseline write latency (a quorum round-trip on every write) and a more significant architectural commitment than adding a failover tool to an existing single-primary database.

**How it backfires:** Doesn't eliminate outages during a partition that isolates a majority of nodes — the system correctly refuses to make progress in that case, which is safe but is still unavailability, not a free lunch.

## Interactions

- [Replication Lag](replication-lag.md) — the promoted replica's remaining lag at the instant of promotion is exactly the data placed at risk of loss.
- [Correlated Failure](../dependencies/correlated-failure.md) — the network partition that triggers a failover often correlates with other simultaneous failures in the same blast radius.
- [Static Stability](../capacity/static-stability.md) — failover automation that depends on a control plane inside the same partition it's trying to route around cannot complete, the same static-stability failure mode seen elsewhere in autoscaling.

## References

- GitHub. **"October 21 post-incident analysis."** *GitHub Engineering Blog*, 2018.
  A detailed, public account of a network partition producing divergent writes across a failed-over MySQL topology and the reconciliation required afterward.
- Corbett, J. et al. **"Spanner: Google's Globally-Distributed Database."** *OSDI 2012*.
  Describes quorum-based (Paxos) leader election per data shard as a structural alternative to heuristic single-primary failover.
- Kleppmann, M. **"How to do distributed locking."** *martin.kleppmann.com*, 2016.
  Introduces fencing tokens as a general mechanism for safely handling a process that may have been superseded, drawing on Google's Chubby lock service.
