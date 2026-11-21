# Direct prepared server endpoints

ReplicatedFormServer keeps its existing endpoint table, scalar argument codec,
required Val parameters, revision/sequence checks and atomic delta admission.
Only the accepted call's execution changes: direct sessions call the existing
prepared declaration factory rather than Interpreter.call_routine. Functions
return their generated Python result; procedure calls return Undefined.

The caller supplies the exact already-bound server routine. The bridge checks
its current registry identity, side, module context, arity and required Val
signature, and matches the prepared descriptor. Each call gets a fresh context,
server/module activation and activation-local module state. Form owner, source
binding and database/writer authority remain with the existing FormBoundary and
public services. No new name-based remote endpoint discovery is introduced.

An owned schema recompile does not replace the original routine metadata
identities held by the endpoint table. It recompiles only the stored source
snapshot, not client-supplied code.

Protocol semantics are unchanged: an accepted failing handler advances revision
and can retain partial in-memory form changes. This is not a database rollback
or a new atomicity promise. Database writes retain their existing writer's
transaction rules. Unknown endpoints, invalid arity, stale revisions and invalid
deltas still fail before handler effects.

The real main-demo document broker/controller open→WriteButton→close test now
passes. Focused tests cover returned function values, procedures without VM
dispatch, rejected requests, source errors and schema refresh identity.
