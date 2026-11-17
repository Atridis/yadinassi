# Bounded session-owned unqualified crossing

An ordinary source host entry may call a zero-argument server routine owned by
its own current session interpreter. The caller must actually enter on the
client side; a logical-side label alone is not authorization. Resolution keeps
existing current-side routine, service and local-callable precedence. Other
application interpreters and foreign sessions do not gain this entry point.

The admitted routine is synchronous, contextual and non-reusable, with no
arguments/defaults or module storage. A private routine may be called because
this is an unqualified call from the same session owner, not a public common
module export. Current session registration, source bytes, plan, declaration
registries and canonical host bindings are checked before effects and again
during the activation and before returning.

The path reuses the qualified ServerCall packet and fresh-activation machinery.
Safe-mode and active-transaction transfer gates run before crossing. The fresh
server interpreter receives copied declarations, empty module storage, disabled
transaction activation and no client application-export capability. Return values
use the existing bounded transfer protocol; foreign runtime handles are not
made transferable. Every exit revokes/closes the activation and restores the
client frame. The scheduler's active frame is correctly server-side during the
server execution; this is not a permanent side change of the caller.

The zero-parameter lazy SessionParameters initializer was already supported.
An independent regression enters it through an existing qualified common-module
ServerCall, separate from this new unqualified path. No VM dispatch, arbitrary
session-side switching, async, NoContext, nonzero-argument or stateful activation
is introduced.
