# Caching

Caching patterns address the failure modes that emerge when services depend on caches
to stay within capacity. The meta-pattern: a cache that works makes your backend look
well-provisioned; a cache that fails reveals that it was the only thing standing
between you and overload.

## Reading order

[Cache as Hard Dependency](cache-as-hard-dependency.md) first — it defines the
fundamental asymmetry. Then [Stampede and Coalescing](stampede-and-coalescing.md)
and [Leases](leases.md) for the concurrent-miss problem. [Slow Cache vs. Down Cache](slow-cache-vs-down-cache.md)
for the counterintuitive failure mode.

## Patterns in this section

- [Cache as Hard Dependency](cache-as-hard-dependency.md)
- [Stampede and Coalescing](stampede-and-coalescing.md)
- [Leases](leases.md)
- [Slow Cache vs. Down Cache](slow-cache-vs-down-cache.md)
- [Hot Keys](hot-keys.md)
- [Cold Restart Warmup](cold-restart-warmup.md)
