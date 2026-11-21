# Lightweight direct common-module reuse

The direct configuration command lane lazily wraps an eligible, qualified,
same-client function on its first call with `functools.lru_cache(maxsize=256,
typed=True)`. Arguments and results remain restricted by the existing scalar
command boundary. Procedures and failed calls are not cached. A cache hit does
not replay the function body's effects, as requested by the module's reuse flag.

`DuringSession` belongs to one application; `DuringRequest` belongs to the
current synchronous command and is created only when first needed. Existing
refresh and close lifecycle operations clear the wrappers. Owner, selected
routine, and capability checks still run on hits. Ordinary functions do not
enter the reuse wrapper. There is no legacy execution fallback.

This is a lightweight approximation, not complete native 1C cache parity. The
256-entry LRU bound is per function; the older shared byte accounting and
age/idle timers are not applied to this direct lane. Those policies remain
unchanged for the older cache implementation. Mutable results, by-reference
arguments, server crossings, and broader service/constructor admission are
outside this slice. In particular, existing native reuse packets that need UUID
constructors or non-Val parameters are not made executable by this change.
Nonfinite Decimal arguments are refused before function effects; finite numeric keys use
Python numeric equality, with top-level types separated by `typed=True`.

Host lifecycle refresh is supported. The BSL `RefreshReusableValues` service
remains outside the scalar command service allowlist in this slice.
