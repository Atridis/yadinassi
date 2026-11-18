# Direct references to detached table fields

Direct reads and writes of `row.Column`, `row[index]` and `column.Title` already
used the public table protocol. Passing those same addresses to a by-reference
parameter instead reached the generic host-member boundary and failed with
`unregistered host member`. The bounded adapter connects exact canonical table
rows and column descriptors to the existing getters/setters. Only rows support
indexed references. It does not expose storage, arbitrary attributes or table
collection replacement.

Binding performs the eager read required by the existing reference contract;
write permission is deferred until the callee actually writes. All subsequent
reads and writes resolve the live public protocol, preserving readonly fields, deletion errors and bounded
slice restrictions. Row-reference writes are restricted to untyped tables with
no indexes; typed/indexed table references remain readable but reject writes
explicitly before the setter or mutation. Ordinary assignments still use their
existing qualifier/index semantics. Aliases observe the same live cell, Val parameters remain
copies, and a successful write before a later exception remains committed to
the detached value. Receiver and index expressions are evaluated once.

The adapter pins its row/column receiver and base-class protocol identities at
model definition time, rejects changed receiver methods/descriptors and instance
method shadows, and checks basic cell/deletion storage shape. It captures the
exact raw owner and rechecks that identity and boundary lifetime on every access
and after every callback. A retained reference cannot be moved to another table
or used after the interpreter closes. This is not a new sandbox for all Python
mutation of the table model: existing public table operations and their guards
remain responsible for schema and value semantics. No database authority is
inferred from a cell payload and no VM fallback is introduced.

Regressions cover source/AST/prepared/Execute/Eval routes, eager binding errors,
readonly deferred writes, aliases, Val, write-then-error, retained references,
owner replacement, closed runtimes, deleted rows, slice writes, hostile index
protocols and replaced receiver hooks. The existing failing table runtime
reference test passes unchanged.

Evidence boundaries: the original eight-record owner table checkpoint is
replayed unchanged and still matches its native fixture. It does not measure
this exact table-field byref combination. Separate canonical-runtime controls
check aliasing, Val and write-then-error behavior; no new native capture or full
native parity is claimed. Source-module table-field reference routing is not independently certified by
this cohort; other unintegrated receiver classes are not added.

## Forged column-key hardening

Review found that an exact dict is not enough for row cell storage: a foreign
key can have a canonical column's hash and invoke its own equality hook during
a cell lookup. Before any public lookup, the adapter now checks every cell key
for exact column identity/type and the same owner, pins column identity hash and
equality, and validates the root's exact column collection, exact items list and
raw column names/owners. Root/column-collection protocol identities are pinned
as well. These checks recur after argument callbacks and for retained references.
Tests cover the forged collision at binding, after another argument and after
capture, plus hostile collection/list/column/name/owner substitutions. No key
comparison or payload conversion is used by this validation.

## Deliberately bounded write delegation

A second review identified that validating a row alone did not authorize its
mutable `indexes` and `value_type` delegates. Row-reference writes now require
an exact canonical empty index collection and exact canonical descriptions with
empty type tuples. Their definition-time class protocols, raw owner/field shapes,
canonical adjust function and bounded index budget are checked before invoking
the setter. Foreign delegates are rejected without attribute access; typed or
indexed writes raise an explicit unsupported boundary error rather than quietly
succeeding. Readonly/deferred-write semantics remain: a readable address may be
passed to a Val/read-only callee, but mutation is rejected before any cell change.
Tests replace each delegate during a later argument and after reference capture;
ordinary typed/indexed assignment is separately checked to remain operational.
