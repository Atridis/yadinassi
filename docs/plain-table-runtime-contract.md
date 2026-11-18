# Lightweight working ValueTable (integration candidate)

This is the actual exported `BSLValueTable` constructor, not a research selector.
Rows are dicts keyed by normalized column names; one schema owns ordered names,
lookup offsets, metadata, and default cells. There is no second mutable cell map.

## Deliberate differences

* Cells default to Undefined. TypeDescription is metadata, not coercion.
* Python scalar ordering replaces 1C-specific ordering. Custom comparators are
  unsupported; sorting rejects opaque objects instead of invoking their hooks.
* Indexes, GroupBy, column insertion/reordering are explicitly unsupported.
* `columns.items` is a readonly tuple; `row.cells` is a readonly inspection
  snapshot. Python callers must use the mutation methods or explicit cold
  materialization setter. Raw mutation compatibility is not promised.
* Codec/query/native compatibility is not yet established. Old assertions are
  retained to measure these differences, not rewritten as successful parity.

## Boundaries retained

Exact receiver classes and definition-time class/function/accessor snapshots,
module binding and keyset checks, exact string keys before hashing/lookup,
owner/schema identity, readonly bounded slices, and context checks remain.
Foreign database receivers gain no authority from being cell payloads.
There is no VM fallback. Per-operation context checks have NOT been hoisted:
GC finalizers and concurrent closure require a separately reviewed contract.

## Evidence so far

22 new storage/runtime tests passed normal and Python 3.10 optimized before the
latest namespace-keyset guard. Actual BSL construction, add/get/field writes and
numeric loops execute the dict-row class with VM entry points patched to fail.
The existing 25-test reference/iteration cohort initially had 5 failures and
6 errors; one real readonly-slice write regression was fixed and its direct
iteration regression now passes. Other identities require final classification,
including intended readonly raw-storage and typed-coercion incompatibilities.
No wall-time claim, production approval, publication or full-green claim yet.

Latest bounded run: 26 new tests normal + Python 3.10-O pass, including explicit
row identity inequality, added-builtin shadow rejection, deleted indexed row,
and readonly slice writes. Existing 25 reference/iteration tests now have
3 failures + 7 errors (15 pass). Raw cells/items injection tests stop earlier
at readonly/materialization APIs; a subclass fixture requires the former row
constructor signature; owner replacement inspection and deleted-row legacy
iteration differ. Native checkpoint and typed/indexed coercion expectations
remain incompatible. Descriptor delegate replacement no longer participates
in writes because descriptors are metadata only; this must be reviewed as a
changed contract, not counted as equivalent guard coverage. These old tests
have not been disabled or weakened.

Integration on unified 14406828 retains table resource limits at growth only:
100,000 rows, 4,096 columns, 1,000,000 cells. Add/Insert/AddColumn fail before
mutation. Query quota removal does not apply to tables. No GC suppression or
loop boundary hoist is used. Its cost must be measured separately.

## Positional replacement

The next candidate replaces each dict row with a list subclass. A shared
`name -> offset` dictionary resolves named access; numeric access indexes the
row directly. Schema containers are lists. AddColumn appends schema entries
and a default to each existing row instead of validating/copying the whole
schema and table. Rename changes only schema names/index, not row payloads.
DeleteColumn remains linear. Explicit admission still validates shape, owner,
exact schema keys, function hooks and readonly context; growth quotas remain.

This deliberately does not provide transactional rollback for MemoryError
midway through schema growth. Failed admission rejects inconsistent storage
on subsequent BSL entry. No new database authority or user callback is granted.
Tuple rows were rejected because ordinary BSL cell assignment would recreate
entire immutable tuples. Direct raw dict-row injection is no longer meaningful;
the hostile-key test instead corrupts the actual shared offset dictionary.

Removed opaque cell payload finalizers can run between kernel schema deletion
and facade column-list update. Reentrant BSL admission must fail closed during
that transition; whole-facade atomic publication is not claimed. The retained
payload kernel guarantee alone is not a guarantee across the facade return.

Final safety preflight: structural AddColumn scans exact schema keys/offsets
and active row identities/lengths before mutation, but not payload cells. It is
O(columns + rows), not O(1) total. Ordinary named lookup also rejects malformed
host offset keys before Python dictionary lookup. This remaining cost is
explicit; no trusted/private schema provenance is claimed. 35 focused tests
pass normal and Python 3.10 optimized, including retained refs across row order
and schema changes, independent copy, actual indexed byref readonly, hostile
AddColumn/named read, and fail-closed finalizer reentry.
