# ValueTree standalone core — bounded native observations and implementation

This checkpoint implements the explicit tree model without claiming full native
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

Primary documentation alone does not settle Find/FindRows/Copy edge contracts.
Rows.FindRows now has a separately authenticated bounded checkpoint and local
alignment; see [search scope and evidence](value-tree-findrows-runtime.md).
Rows.Find now has a separately authenticated 44-observation checkpoint and bounded
implementation; see [current scope and acceptance gates](value-tree-find-runtime.md).
Rows.UnloadColumn has an authenticated 30-observation checkpoint and bounded
implementation; see [scope and acceptance gates](value-tree-unload-column-runtime.md).
Rows.LoadColumn has 45 authenticated observations and accepted runtime gates; see
[LoadColumn scope and evidence](value-tree-load-column-measurement.md).
Rows.Move now has 32 authenticated observations and a bounded implementation; see
[runtime scope and pending fresh acceptance](value-tree-move-runtime.md). Copy remains deferred. Local-only tests are not native evidence.
Rows.Total has32 authenticated observations and a bounded implementation; see
[Total scope and pending fresh acceptance](value-tree-total-runtime.md).

## First authenticated native capture and display correction

[Run 40221284540, attempt 1](https://github.com/Atridis/yadinassi/actions/runs/40221284540)
executed head `ba32da0e2640046f320b4e7c982c77ed10a680df` via merge checkout
`58487b6d85689e76e4e91dc73c709650ef13efd9`. Its comparison **failed**: record 856,
`tree.core.types`, differed only in five type display labels. The other eleven
new tree records matched byte-for-byte. The eight other differing records were
already eligible historical Map observations; no comparison tolerance changed.

The captured `String(TypeOf(...))` labels are:

- `Дерево значений`
- `Коллекция строк дерева значений`
- `Строка дерева значений`
- `Коллекция колонок дерева значений`
- `Колонка дерева значений`

Only `BSLType` presentation is corrected. Unspaced Russian and English Type/
constructor aliases remain unchanged; spaced displays are not added as aliases.
This record does **not** measure `String(tree)` or other object `__str__` methods,
so those implementations are untouched.

The same bounded capture observed levels `0;1;2;0`, parent/owner identities,
shared numeric defaults and assignment, row access, one-of-two-column deletion,
and child clearing. The retained grandchild read then produced `error`: evidence
of a rejected read, not successful detached-row behavior. These observations do
not establish every edge case listed below. Fresh CI/native acceptance after the
display correction is still required; the failed report discarded the optional
core witness token and is not a successful full-core acceptance result.

Authenticated six-output artifact: ID `12609735687`, 39,298 ZIP bytes,
SHA256 `1d4cf9d36b5350513ba4ac5b4f78119c4de3c40f52a98e325364191199113a4f`.
Native output bytes, fixtures, source probes and capture gates were not rewritten.

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

Except for the separately measured method-local UnloadColumn/LoadColumn, Move and Total conversions,
strict finite integral in-range indices only; tree column widths must be integral
and in 0..2^32-1. No implicit ValueTable index coercion is assumed. Names matching
Rows/Parent or Russian equivalents are rejected, including rename. Deleting the
last column of a populated tree or clearing its columns is rejected before any
mutation. Deleted object lifetime/presentation is not claimed as compatible.

No Copy, Sort, UI,
XML/internal serialization or transport. Internal serialization also explicitly
rejects Type("ValueTree") and the four dependent type identities, rather than
inventing native UUIDs. Object string presentations and conversion edge cases remain unverified; the
five type displays above are the separately measured exception.

`FillValues / ЗаполнитьЗначения` is a ValueTable method, not a missing tree
feature. The [API inventory and negative regression](value-tree-fill-measurement.md)
explain the corrected scope; no invented tree method is added.

## Resource limits (Yadinassi limits, not platform limits)

Whole-tree maxima: 100,000 rows, 4,096 columns, 1,000,000 cells; maximum row level
256. Aggregate immutable string-default content is capped at 1,000,000 characters
across columns; padded defaults are shared by rows rather than reallocated. These include all descendants, including trees with no columns. Add and
column insertion check budgets before mutation. Shared-schema operations and
subtree deletion are iterative; no host recursion follows tree depth. Existing
column text/type-conversion limits are retained. No limits or security checks
were loosened.
