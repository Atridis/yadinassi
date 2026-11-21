# Module visibility at external edges

The previous module-locals implementation copied every source slot to public
state and reloaded every slot around each Binary/Unary/Attribute/Index/Call.
That introduced O(expression executions × module slots) namespace work, plus
O(source expressions × module slots) generated synchronization code. It also
made a native table workload much slower than the preceding compiler.

The revised compiler emits one publisher and one reloader per generated module.
Synchronization is selected at actual external call/receiver edges, not scalar
arithmetic. Exact canonical native container receivers avoid namespace copying;
their existing authority resolvers and checks are still called. Receiver binding,
argument evaluation and execution remain single-emission. Unknown receiver
resolution/getter/call is inside the synchronization boundary. Exceptional exits
reload via the enclosing generated finally. The publisher checks the original
context before its first write and after every write.

Code devoted to synchronization is O(source edges + module slots). Runtime
namespace copying is O(actual external crossings × module slots), not O(native
expression operations × slots). Native receiver classification is constant-size
identity-only work. This is not a proof that the complete parser/compiler is
linear, and preparation/unparse remain separate passes.

Intentional compatibility change: callbacks from opaque Python arithmetic,
private monkeypatches, or opaque payload finalizers inside canonical containers
are not namespace-publication points. They may observe the most recently
published snapshot rather than every intermediate BSL local. Their execution is
not newly authorized by this change. Native operation authority checks, actual
external capability resolution, close/revoke checks and publication checks remain.
The compiler does not claim that native operations are universally callback-free.
Owned/source profiles do not use this module-local optimization.

Tests include constant publication count for a growing native table workload,
linear synchronization-code size, trusted explicit host receiver get/set/call
visibility, exceptional reload, fatal close, and existing public host-service,
by-reference and publication security regressions. No full compatibility claim.

Security correction before integration: removing namespace copying must not remove
liveness. An opaque arithmetic callback can close the VM before a subsequent Add
on a preexisting public array. Unknown arithmetic now checks liveness after its
result; low-level native operations check before/after and after actual argument
evaluation, immediately before invocation. Native writes check after RHS before
the store. These checks do not copy/reload slots. Whole-module proven private
numeric paths remain unchanged. Canonical table/list operations retain their own
existing authority checks; no blanket claim of callback freedom is made.
