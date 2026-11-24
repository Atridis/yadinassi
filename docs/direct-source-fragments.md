# Bounded direct source Execute and Eval

Ordinary exact source boundaries admit dynamic statement and expression fragments
through the existing direct compiler and FragmentScope. There is no new interpreter,
VM fallback or replacement owner. Imports/declarations in Execute remain forbidden
by parse_fragment before effects. Source forms, object-handler and NoContext
boundaries are deliberately excluded from this slice.

Visible local/byref addresses and module slots remain live. Source application
exports resolve through their existing owner checks, while visible local bindings
shadow external names. New fragment-only names are private and disappear at exit.
Source constructors and qualified call admission use the source profile; Eval's
returned expression requires a value, rejecting procedures before argument effects.

Each fragment gets a separate safe-mode routine frame. It inherits caller restrictions
but cannot disable a caller's counter; its own counter is cleaned on normal and
exceptional exit. Existing request scope and transaction/transfer authority remain
unchanged. Shared source Execute/Eval depth counters survive transitions through
new source-routine boundaries, preventing depth reset through recursive helpers.
Counter shape, identity and expected level are checked before cleanup arithmetic.

Prepared source fragment caches are private, weakly keyed by exact active boundary
and released when it leaves. They retain compiled code/constants and facts, never
live bindings, scopes or grants. The source profile and visibility layout are part
of the exact key; warm execution repeats admission and uses the fragment's own
source text for diagnostics. Original text/depth/cache size limits remain.
Injected public cache attributes reject before lookup; stale FragmentScope
references reject after exit.

Standalone and owned source caches use the same admission policy. Compiled units
fit the unchanged 16-entry and source-character bounds. At either bound, a new
unit displaces prior units only after a repeated successful miss; the small
history stores only process-local hashes, not fragment text, code or bindings.
One-off misses cannot flush the hot set, while a changed workload can incur
one extra preparation pass before its new set becomes resident (if it fits).

Lifetime VM-poison tests cover safe-mode cleanup, exported slots, byref mutation,
local shadowing, nested depth, source constructors, retained references, changed
bindings, early qualified-call denial and unsupported boundary subclasses.
