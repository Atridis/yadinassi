# Generated document posting

The direct backend now executes source-bound document callbacks as generated
Python functions. `_PostingInterpreter` remains a metadata/service holder; its
`call_routine`, `block`, and AST visitor are not the execution path. Other
backends retain their existing path.

`PostingRuntime.write` remains unchanged: canonical configuration/source
selection, typed document/line buffers, writable checks, journal savepoint,
movement staging, cancellation, commit/rollback and uncertain-write handling
are still owned by the existing writer. Generated handlers run under
`admission(False)`, including callbacks through parent-bound output services.
They cannot take ownership of the transaction. Boolean cancellation is checked
at the same event boundary.

The boundary exposes the current document and objects reached through its
public buffer/query protocol. It uses no arbitrary Python attribute reflection.
Document methods cannot recursively write from this boundary. Movement field
coercion, exact enum types, row attachment and recorder ownership remain in the
existing public objects. AdditionalProperties is the existing mutable Structure;
its Property output receives a canonical Reference, not a copied scalar.

No per-AST-step MAX_STEPS observer is carried into this path. Existing storage
and public movement buffer constraints are untouched. This does not claim
resource isolation or arbitrary Python host-code sandboxing.

The first implementation prepares the declaration factory per event. It does
not cache authority or event closures; preparation reuse is follow-up work.
Diagnostics currently identify `<document-posting>` and AST source positions,
without reconstructing original source excerpts. Unsupported host collection
shapes and captured method values fail explicitly; this is not full legacy
handler compatibility.

Focused tests execute original main-demo Receipt source: successful posting
without interpreter call dispatch, Mode 1 cancellation and Mode 2 exception
*after* explicit movement write and an in-transaction query (Inside=1), no SQL
partial writes, non-Boolean cancellation, and a parent-bound output callback
attempting to commit the handler's transaction. Detached buffer/Ref changes are
not claimed to roll back with SQL.

Review regressions also cover closing the parent interpreter from a host output
callback: the child must reject its now-revoked family before committing, and
SQL stays unchanged. Direct handlers retain server/module context with cleanup.
Host-invoked posting explicitly scopes the owner's native target; an actual
Linux-owner callback previously observed the Windows default and is now tested.
