# Direct AST owned routines

The compiler emits Python functions and lexical locals for one explicitly selected
side. Server, no-context, dual and initializer factories no longer invoke the old
text emitter. The existing crossing adapter remains responsible for side selection,
transfer/copyback, lifecycle and current registry signatures; compilation grants
none of these privileges. Plain uninitialized lexical reads fail when executed,
not when compiling an unreachable branch.

Source routines use one existing `routine_scope()` safe-mode frame per call,
including recursion and default evaluation. That frame checks owner state on entry
and in `finally`; redundant adjacent generated entry/exit checks are not copied.
Local call resolution checks before argument effects; the callee's frame checks
again after argument evaluation. These protect different mutation points.
Authority profiles retain loop checkpoints. Ordinary arithmetic, assignment and
branching remain Python operations, not statement-dispatch helpers.

Source lexical presence uses explicit sentinels rather than a `locals()` snapshot.
The special manager/XDTO implicit-shadow rule retains external lookup until first
assignment, and its existing Execute/Eval combination remains rejected. Canonical
byref storage, source-qualified arity/output-shape preflight, scalar-reuse entry and
result validation, export identities and current layout checks remain in place.
No old compiler or interpreter is retried on preparation or execution failure.
Source-owned Execute/Eval integration is a separate companion slice, not implicitly
accepted by this change.
