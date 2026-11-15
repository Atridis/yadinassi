# Server common-module reuse: acquisition preparation

This is authored acquisition source, not runtime support or observed parity.
It remains separate from the fixed language aggregate and client-only reuse.
A dedicated staged host adapter and owner/branch-pinned native workflow are
prepared. Production admission is not enabled by these files. No native evidence
has been acquired yet.

Four non-global, non-privileged modules distinguish server-only session/request
caches, a reusable ServerCall module, and an uncached scalar-only inspector.
The managed-client form uses two real events. Sixteen observations cover client
hits, key separation, the direct server result, client-only refresh, server-only
refresh, both refreshes, qualified and unqualified server calls, request pairing
inside one RPC, request separation across RPCs, server session retention, failure
retry, argument evaluation and cross-event retention. Case 15 checks a second
request-local pair after intervening operations, before the event boundary.

UUID strings only identify computations inside the packet. Records contain
booleans/counts or explicit `error`, never raw identifiers. No expected answers
are substituted. Actual native evidence is required before runtime implementation.

The official reference describes two separate caches for reusable ServerCall
modules: https://1c-dn.com/library/specifics_of_reusing_return_values/
This packet intentionally does not expand the existing scalar transport. Returned
object aliasing across transport, global modules, asynchronous calls, server pool
reuse across sessions, TTL timing and privileged execution remain unclaimed.

## Integration boundaries observed in the current implementation

* `configuration_modules.parse_common_modules` currently rejects server reuse.
* Remote stubs are distinct routines and absent from the client reuse registry.
* `_invoke_remote` creates a server `run_inline` request boundary per invocation.
* `ApplicationReusableValues.authorize` currently requires the client side.
* Client cache hits must occur before transport invocation; server cache hits must
  remain in the server family. Neither may share mutable ownership or epochs.
* A qualified server direct call and a remote endpoint invocation enter different
  interpreter paths today. Admission and cache selection must explicitly account
  for both, rather than merely remove the client-only guard.

The packet retains the existing source/hash/nonce-bound two-event format but has
its own schema and SR record prefix. The dedicated host adapter must stage
exactly these four modules and validate the full disposable-baseline inventory.
