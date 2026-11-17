# Direct source same-side reusable functions

Qualified synchronous common-module functions can reuse results in the existing
application-owned DuringSession and DuringRequest caches. This bounded adapter
requires explicit Val parameters without defaults. It does not enable ServerCall
reuse, asynchronous continuations, NoContext or global reusable modules.
Unqualified private calls retain ordinary generated execution, without caching.

Reuse is not an authorization cache. Every invocation checks the actual caller,
owner, generated declaration, module provenance and original source/metadata
inventory before argument effects and again after them. Canonical cache/store
hooks, exact ownership pointers, stored key/entry shapes and accounting are
validated before lookup. Hits remeasure the retained result and repeat admission;
invalid retained values are discarded. Cache values retain their existing alias
identity, while bounded immutable snapshots are used only for accounting.

Misses reserve an epoch, execute the generated function, reauthorize and measure
before publication. Failure does not publish. RefreshReusableValues during the
computation invalidates the reservation, preventing stale publication. Existing
age, idle, entry and retention limits remain authoritative. Same-side reuse does
not invent a cross-context transfer or relax transaction/safe-mode checks.

Direct source root execution now owns a synchronous request scope. Nested generated
calls share its cache; root cleanup clears the exact captured dictionary and
restores the preceding scheduler context. Context/cache replacement fails closed.
No scheduler runner or legacy interpreter dispatch is used to implement this scope.

Tests replay existing session/request/refresh/isolation observations under lifetime
VM poison and cover private helpers, failures, typed scalar keys, expiration,
foreign/replaced authority, argument-time mutation and cache/factory tampering.
This change makes no performance claim and keeps unsupported key/result kinds
closed under the existing canonical argument and snapshot contracts.
