# Direct source scalar ServerCall reuse

The existing qualified source ServerCall adapter now admits the existing closed
scalar reusable module profile. The module must be server-only, non-global,
non-privileged and have DuringSession or DuringRequest reuse. Every declaration
must be a synchronous function with explicit Val parameters and no defaults.
Ordinary DontUse ServerCall keeps its separate literal-default contract.

Cache authority belongs to the registered origin, never to a fresh activation.
Crossing calls and same-server qualified calls share the canonical server cache
key. Every warm hit repeats source provenance, caller context, ownership, cache
accounting and scalar validation. Client calls still pass safe-mode and transaction
transfer admission before argument effects and again after them, before lookup.
All argument effects and late named-value reads complete before a key is formed.

A cache miss uses the existing fresh generated source activation and bounded
incoming/outgoing packet transfer. Returned scalars are checked before publication.
Failures do not publish; refresh during computation invalidates its reservation.
The outer synchronous request cache is shared across nested fresh activations and
cleared on root completion or failure. Session cache remains application-owned.

Private/unqualified calls remain uncached. Their scalar contract is not implemented
only in the dispatcher: source-only code generation validates every routine's
parameters before its body and every explicit returned value before returning to
its lexical caller. This closes direct fnN-to-fnN calls as well as public exports.
The scalar-generation flag is sealed into the prepared plan and checked against
the active owner, including fresh activations. Standalone code generation does not
enable this internal option, and it requires trusted source scopes.

Lifetime VM-poison replay checks all 16 recorded native local/file-mode observations,
including shared crossing/same-side keys, private helper behavior, refresh, session
and request lifetime. This is not a split-server cache or a new native platform
claim. Copyback, async, NoContext and non-scalar reusable values remain unsupported.
