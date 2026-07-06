# Overload

Overload patterns describe what happens when a service receives more work than it can
process. They are the most cross-referenced section because almost every other pattern
either causes overload, is caused by overload, or is a mitigation for it.

## Reading order

Start with [Goodput Collapse](goodput-collapse.md) — it defines the failure mode
everything else references. Then [Retry Storms](retry-storms.md) and
[Metastable Failures](metastable-failures.md), which show how overload becomes
self-sustaining.

[Queue Management](queue-management.md) is the mechanism; [Load Shedding](load-shedding.md)
and [Backpressure](backpressure.md) are the primary mitigations. [Adaptive Concurrency](adaptive-concurrency.md)
and [Deadline Propagation](deadline-propagation.md) are the tools that make shedding
and backpressure safe.

## Patterns in this section

- [Goodput Collapse](goodput-collapse.md)
- [Load Shedding](load-shedding.md)
- [Retry Storms](retry-storms.md)
- [Backpressure](backpressure.md)
- [Queue Management](queue-management.md)
- [Deadline Propagation](deadline-propagation.md)
- [Adaptive Concurrency](adaptive-concurrency.md)
- [Metastable Failures](metastable-failures.md)
