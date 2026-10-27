# ValueTree Rows.UnloadColumn — bounded implementation, acceptance pending

This method returns a new mutable Array containing one selected cell from each
immediate row of the receiver, in current row order. It does not traverse
children or use the insertion-order tree-wide row registry. Both English and
Russian method names are supported on row collections, not on the tree itself.
Array membership is independent of later source-row additions and result-array
deletions. Cell references are forwarded without conversion, equality, deep copy
or user-defined hooks.

## Native evidence and limits

The original 27 observations from [run40496124727](https://github.com/Atridis/yadinassi/actions/runs/40496124727)
are retained separately, byte-for-byte. A supplemental capture,
[run40525937279](https://github.com/Atridis/yadinassi/actions/runs/40525937279),
authenticated all 30 observations (19 successes, 11 action errors), and its first
973 native records exactly match the previous capture. Both runs failed host
collections comparison before implementation. Neither is runtime acceptance.

Root rows produce Id values [1,2], child rows [4,5], empty leaf/tree receivers []
when the column exists. A column must be resolved before an empty-row shortcut:
unknown names and a nonexistent column on an empty-schema tree still fail.
Names are case-insensitive; a live own-tree column object is accepted, a foreign
column is rejected. Scalars preserve Number versus Boolean and Undefined versus
Null. Two-direction mutation of one Structure.Mark field establishes shared cell
identity independently of result-array membership. It does not establish all
object classes, detached-row lifetime, exception type or exception text.

Numeric selectors 0/1/0.5/1.5/1.9/-0.5 select columns 0/1/0/1/1/0. The last three
witnesses distinguish truncation toward zero from rounding or floor. The method
therefore applies that rule to resource-bounded finite Decimal selectors, checks
the truncated index against the schema, and only then converts to a Python int.
General finite-number handling beyond these witnesses is a local implementation
rule, not an exhaustive native measurement. Boolean/Undefined/Null/unknown object
selectors are not numerically coerced. Existing shared tree `_position`, row and
column Get/Insert rules, Find and FindRows are unchanged.

Forwarding other opaque cell objects by identity is likewise a local
implementation generalization. The native reference witness is only the bounded
one-field Structure, not arbitrary object or serialization compatibility.

## Local safety/resource policy

Existing whole-tree limits remain unchanged: at most 100000 rows and 4096
columns. The method checks immediate-row and schema sizes before iteration,
ordinary internal list/dict containers, live owned rows and live owned columns.
Name normalization and numeric validation reuse the bounded search budget:
1000000 text units, 8000000 work units and bounded finite Decimal coefficients.
The result holds at most one reference per immediate row. It never recursively
walks or serializes a cell; large numeric exponents cannot trigger unbounded
integer allocation because range checking precedes integer conversion.

Missing/extra arguments and wrong receivers reject through existing dispatch.
Local tests also cover malformed storage, hostile selector hooks, detached
objects and resource limits; these are local safety rules, not new native cases.
No LoadColumn, Copy, Sort, UI, transport, codecs or database semantics are added.

## Acceptance gate

`tests/test_value_tree_unload_native.py` binds exact source and literal capture
hashes, preserves the original 27 ledger, and replays individual and complete
native observations without filtering. Local passes alone are insufficient.
Fresh complete native/full-host, source/full138, binary/package and four-platform
checks must cover the final implementation and its new runtime digest. Existing
old946 comparisons and eight Map allowances are not weakened.
