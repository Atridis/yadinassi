# Direct client call to a bound replicated-form endpoint

The real Receipt `AddLineCommand` calls `AddAtServer`. ReplicatedFormSession
already installs a server routine stub and an invocation binding whose transport
is `_request('call', ...)`. The direct compiler previously resolved only ordinary
registered host functions, rejecting `addatserver` before any row was added.

FormBoundary now resolves this explicit prebound form invocation. It captures
the binding and required Val signature, checks the current stub/binding identity,
logical client side and configuration permission before returning a callable,
and rechecks them before transport. A procedure requested as a value is rejected
at binding time, before argument evaluation. Argument count is checked before
transport; this does not introduce a general pre-argument arity analysis.

The existing request path still owns scalar argument encoding, revision/sequence,
endpoint selection, uncertain-outcome locking, accepted state replication and
server-side execution. No AST VM fallback, arbitrary callable lookup or writer
bypass was added. Returned direct callables do not survive binding replacement,
changed signature, closed family or a change to the logical server side.

This slice supports ReplicatedFormSession module-context server stubs. Ordinary
NoContext InvocationPort bindings remain unsupported here. It is not a generic
cross-context runtime replacement.

Focused coverage invokes the original Receipt AddLineButton through the real
MainDemoHost/application protocol with legacy call_routine disabled. It asserts
one replicated line, Quantity=1, Amount=0 and Dirty=True. Additional cases reject
retained binding replacement, signature change, wrong side/arity/result kind and
closed owner before transport. Browser QA remains a separate end-to-end check.
