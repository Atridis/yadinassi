# ValueTree standalone core — native-unverified

This checkpoint implements the explicit tree model without claiming native
parity. Local tests are `tests/test_value_trees.py`; no native fixture or harness
is changed by this implementation. Package version stays 0.4.2.

## Evidence boundary

Official 1C documentation establishes the ValueTree family and client-availability
boundary, but does not establish the edge semantics below:

- [Official 1C compatibility change notes](https://1c-dn.com/library/v8update_026v8_fbco_changes_that_require_modification_of_configuration_and_administrative_settings/)
  identify the row, row collection, column and column collection types and their
  exclusion from modern thin-client code.
- [Official 1C collection-search guidance](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Developer_Guides/1C_Enterprise_Development_Standards/Code_conventions/Using_applied_objects_and_universal_value_collections/Searching_in_collections/)
  distinguishes tree scanning from ValueTable search indexes. No table-index
  machinery is attached to this tree implementation.

Primary documentation located so far does not settle Find/FindRows/Copy argument
or traversal contracts; these are intentionally not implemented. Local tests
must not be relabeled as native evidence. Native measurement is a separate track.

## Implemented local contract

- One tree-wide column schema, including columns added after children exist.
  Column values use existing TypeDescription defaults and adjustments. Cells
  keep untyped object values by identity, not by deep copy.
- Rows belong to exactly one immediate collection. Count, Get, IndexOf and
  iteration are local to that collection, not recursive. Root level is 0;
  Owner returns the tree; Parent of a root row/collection is Undefined.
- Adding/inserting returns a new row. Deletion and clearing remove the entire
  subtree iteratively and invalidate held descendant rows and child collections.
- Typed Type/TypeOf names for all five ValueTree family objects; only ValueTree
  is directly constructible. No access to Python internals is added.
- Read-only hierarchy/schema properties. Named/indexed cells and column metadata
  use explicit reference slots, consistent with existing runtime dispatch.

## Conservative restrictions pending native measurements

Strict finite integral in-range indices only; tree column widths must be integral
and in 0..2^32-1. No implicit ValueTable index coercion is assumed. Names matching
Rows/Parent or Russian equivalents are rejected, including rename. Deleting the
last column of a populated tree or clearing its columns is rejected before any
mutation. Deleted object lifetime/presentation is not claimed as compatible.

No Copy/Find/FindRows, Move, Sort, Total, FillValues, LoadColumn, UnloadColumn, UI,
XML/internal serialization or transport. Internal serialization also explicitly
rejects Type("ValueTree") and the four dependent type identities, rather than
inventing native UUIDs. Native object/type string presentations and conversion
edge cases remain unverified.

## Resource limits (Yadinassi limits, not platform limits)

Whole-tree maxima: 100,000 rows, 4,096 columns, 1,000,000 cells; maximum row level
256. Aggregate immutable string-default content is capped at 1,000,000 characters
across columns; padded defaults are shared by rows rather than reallocated. These include all descendants, including trees with no columns. Add and
column insertion check budgets before mutation. Shared-schema operations and
subtree deletion are iterative; no host recursion follows tree depth. Existing
column text/type-conversion limits are retained. No limits or security checks
were loosened.
