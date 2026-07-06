# References

Annotated bibliography, grouped by topic.

---

## Foundations

- Dean, J. and Barroso, L.A. **"The Tail at Scale."** *Communications of the ACM*, 56(2), 2013.
  The canonical treatment of tail-latency amplification in fan-out systems. Required reading before building any service with subtask fan-out. Source for the P(max > t) = 1 − (1−p)^N formula and hedged requests.

- Little, J.D.C. **"A Proof for the Queuing Formula: L = λW."** *Operations Research*, 9(3), 1961.
  The original proof of Little's Law; the foundation for thread pool sizing, queue sizing, and connection pool math throughout this guide.

- Mitzenmacher, M. **"The Power of Two Choices in Randomized Load Balancing."** *IEEE TPDS*, 2001.
  Proves that picking the least-loaded of two random choices gives O(log log N) expected maximum load vs. O(log N/log log N) for round-robin. Foundation for power-of-two-choices load balancers.

- Beyer, B. et al. **Site Reliability Engineering.** O'Reilly, 2016.
  The comprehensive practitioner reference for SLOs, error budgets, and reliability engineering at scale. Chapters 17–20 cover capacity planning and autoscaling.

---

## Overload and Stability

- Brooker, M. **"Metastable Failures in Distributed Systems."** *HotOS 2021*.
  Introduces the formal model of metastability: a system that reaches a bad state under high load and has a self-sustaining mechanism that prevents recovery.

- Brooker, M. **"Metastable Failures in the Wild."** *OSDI 2022*.
  Follow-up to the HotOS '21 paper with production case studies. The retry storm and cold-cache examples are traced to real incidents.

- Amazon Web Services. **AWS Builders' Library** (multiple essays). https://aws.amazon.com/builders-library/
  Essays on timeouts and retries, load shedding, static stability, and shuffle sharding. Practical, production-tested guidance from a team operating at extreme scale.

- Krishnamurthy, D. et al. **"A Critical Look at Decentralized Adaptive Concurrency Control for Web Services."** *IEEE ICWS 2003*.
  Analysis of adaptive concurrency control algorithms; the gradient-based approach from Netflix's Concurrency Limiter library derives from this line of work.

---

## Caching

- Nishtala, R. et al. **"Scaling Memcache at Facebook."** *NSDI 2013*.
  Describes the lease mechanism for solving thundering-herd and stale-set problems at scale. The primary reference for the leases, stampede-and-coalescing, and cache-as-hard-dependency patterns.

- Berger, D. et al. **"Adaptive Software Cache Management."** *SIGMETRICS 2018*.
  Covers TTL selection, stale-while-revalidate, and the implications of cache size on cold-restart recovery time.

---

## Load Balancing and Consistent Hashing

- Karger, D. et al. **"Consistent Hashing and Random Trees."** *STOC 1997*.
  The original consistent hashing paper; introduces the ring structure and virtual nodes. Foundation for the consistent-hashing pattern page.

- Mirrokni, V. et al. **"Consistent Hashing with Bounded Loads."** *SODA 2018*.
  Extends consistent hashing with a load cap per node; prevents hot-spot accumulation at the cost of slightly less perfect key affinity.

---

## Queuing and Pipelines

- Welsh, M., Culler, D., and Brewer, E. **"SEDA: An Architecture for Well-Conditioned, Scalable Internet Services."** *SOSP 2001*.
  Original staged event-driven architecture paper. Introduces per-stage queues, backpressure, and the "well-conditioned" service concept. Foundation for staged-architectures and concurrency-models pages.

- Nichols, K. and Jacobson, V. **"Controlling Queue Delay."** *Communications of the ACM*, 2012.
  Introduces CoDel (Controlled Delay), the active queue management algorithm that targets sojourn time rather than queue length. The mechanism behind modern AQM and queue-sizing-by-deadline.

- Shreedhar, M. and Varghese, G. **"Efficient Fair Queuing Using Deficit Round-Robin."** *IEEE/ACM TON*, 1996.
  The DRR algorithm; O(1) per-packet fair queuing that approximates WFQ without the heap overhead. Foundation for the fair-scheduling pattern page.

---

## Multitenancy and Fault Isolation

- MacCárthaigh, C. **"Shuffle Sharding: Massive and Magical Fault Isolation."** *AWS re:Invent 2014* / AWS Builders' Library.
  Introduces the (K/N)^K blast radius formula and production examples from Amazon Route 53.

- Demers, A. et al. **"Analysis and Simulation of a Fair Queuing Algorithm."** *SIGCOMM 1989*.
  The original weighted fair queuing paper; introduces the virtual clock mechanism. Foundation for WFQ-based multi-tenant scheduling.

---

## Inference Serving

- Yu, G. et al. **"ORCA: A Distributed Serving System for Transformer-Based Generative Models."** *OSDI 2022*.
  Introduces continuous batching (iteration-level scheduling); demonstrates 2–23× throughput improvement over static batching. The mechanism reference for continuous-batching.

- Kwon, W. et al. **"Efficient Memory Management for Large Language Model Serving with PagedAttention."** *SOSP 2023*.
  Introduces PagedAttention and the vLLM system. Measures 60–80% KV fragmentation waste in production workloads; shows 2–4× throughput improvement. Primary reference for kv-cache-pressure.

- Agrawal, A. et al. **"Sarathi-Serve: Efficient LLM Serving by Pioneering Chunked-prefills and Preemptions."** *OSDI 2024*.
  Introduces chunked prefill to eliminate prefill-decode interference and enable fine-grained preemption. Foundation for prefill-vs-decode and priority-and-preemption.

- Zhong, Y. et al. **"DistServe: Disaggregating Prefill and Decoding for Goodput-optimized Large Language Model Serving."** *OSDI 2024*.
  Proposes prefill-decode disaggregation; defines TTFT and TBT SLO dimensions formally; shows 2–3.8× goodput improvement from disaggregation. Foundation for token-level-slos and prefill-vs-decode.

- Patel, P. et al. **"Splitwise: Efficient Generative LLM Inference Using Phase Splitting."** *ISCA 2024*.
  Architecture-level analysis of prefill/decode phase splitting; shows that each phase saturates a different hardware resource; includes analysis of when communication overhead negates disaggregation benefit.

- Zheng, L. et al. **"SGLang: Efficient Execution of Structured Language Model Programs."** *arXiv 2312.07104*, 2024.
  Introduces RadixAttention for prefix-aware KV reuse; describes the routing algorithm and 1.1–2.5× throughput gains on prefix-heavy workloads. Foundation for prefix-caching.
