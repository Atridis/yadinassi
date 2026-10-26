# ValueTree Rows.FindRows — measurement-only candidate

This local checkpoint adds 36 **inputs**, not native expected results or a
FindRows implementation. The receiver is `ValueTreeRowCollection`:
`Tree.Rows.FindRows(Filter [, IncludeSubordinates])` or `Row.Rows.FindRows(...)`.
`НайтиСтроки` is measured separately from `FindRows`. Calling the tree or row
itself is a separate invalid-receiver observation, not a supported API claim.

## Primary API evidence and unresolved semantics

The primary 1Ci-Company/Jet code is pinned to
`80884def67e2a75185452a6a13ff394075e457e0`:

- [UsersInternalCached, lines 334–353 and 521–539](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/CommonModules/UsersInternalCached/Ext/Module.bsl#L334-L353)
  constructs a ValueTree and calls root/child `Rows.FindRows` with a Structure and
  explicit `True`.
- [PrintManagementInternal, lines 1325–1330](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/CommonModules/PrintManagementInternal/Ext/Module.bsl#L1325-L1330)
  uses explicit `False` and indexes the returned result.
- [PlacementInSections, lines 104–114](https://github.com/1Ci-Company/Jet/blob/80884def67e2a75185452a6a13ff394075e457e0/cf/Catalogs/ReportsOptions/Forms/PlacementInSections/Ext/Form/Module.bsl#L104-L114)
  iterates the result and modifies found rows.

These examples establish usage, **not** default recursion, traversal order,
empty-filter behavior, scalar equality, coercion, invalid-input outcomes or
reference identity. Do not copy ValueTable empty-filter/equality semantics or
infer search traversal from the interpreter's tree row-registration inventory.

## Fresh setup and 36-record matrix

Every record builds its own tree and filter. A has A1/A2; A1 has A11; B has B1.
Creation order is A, B, B1, A1, A2, A11, with numeric IDs 1..6 in that order.
This distinguishes creation order, depth-first hierarchy order and breadth-first
order without declaring which is correct. All searches use untyped columns.
There are at most seven nodes, including the single added node with ID 7.

| Ordinals | Inputs / observations |
|---|---|
| 867–870 | Root Rows: RU/EN aliases, True, False, omitted flag |
| 871–874 | Child Rows: True/False/omitted; empty leaf collection |
| 875–879 | No matches; matching descendants below nonmatching parents; two-condition conjunction; reversed Structure field order; column-name case |
| 880–881 | Empty Structure on nonempty and empty collections |
| 882–886 | Number 1 and Boolean True queried separately against the same fresh mixed cells; string case; trailing space; Undefined; Null |
| 887–891 | Result→original mutation; original→saved result mutation; delete only result-array element; add node then compare saved/new results; change filter then compare saved/new results |
| 892–893 | Unknown column on nonempty/empty collections |
| 894–897 | Missing filter; Undefined/Number/FixedStructure filter |
| 898–900 | Undefined/Number/String recursion flag |
| 901–902 | Wrong receiver: tree; row |

Both queries within a paired observation share only that record's fresh setup.
Neither a result's expected count/order nor expected success/error is embedded in
source. Invalid-input cases that succeed natively remain evidence requiring an
explicit later implementation/coverage decision; they may not be dropped,
waived or silently declared unsupported.

## Bounded, independent observation

`setup-error`, `action-error`, `change-error` and `observer-error` are distinct.
The search action is separate from a subsequent mutation or second query: a
failed mutation cannot erase a successful search's result. After an action
failure the observer still reads the original six known nodes and local
collection counts. No exception text is emitted.

Result observation records a fixed ASCII type tag, count ≤ 7 and ordered numeric
IDs 1..7. Source-state observation reads all original Id/Key/Group/Mark cells and
seven local collection counts, so failures and array deletion cannot masquerade
as an empty unchanged tree. String cells are projected to bounded ASCII character
codes, preserving case/trailing spaces; Boolean/Number/Undefined/Null retain
distinct tags. No tree serialization or arbitrary object presentation is used.

Reference identity is tested by mutation in both directions, not merely row
comparison. Saved/new results expose snapshot versus later-tree/filter behavior.
A result observer failure is never converted to an empty array or action error.
Each complete record has a conservative 2048-byte ASCII bound including its
label, two maximal result summaries and full source-state summary. The tests
exercise that complete bound, not only the successful normal result.

## Exact source and historical replay boundary

The baseline collections866 is 4000 lines / 312961 bytes, SHA256
`b12fb063732fa8ea16a6e0e88e56d6da99c5958989c9533a07870aee07b72c27`.
Helpers are inserted before the executable body and calls appended at the end;
the old source is therefore **not** claimed to be a byte prefix. The exact
source-only inverse removes precisely these two blocks and restores every old
byte, then the existing historical inverse chain runs unchanged.

Current collections902 is 4241 lines / 327655 bytes, SHA256
`5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782`.
The generated full-client module SHA256 is
`6828717dcc15fbf02e9b4032952b85286dda4b1d6d597e41ffd4a7306f17be31`.
The source-specific adapter pins 124 helper declarations/endings, 16 message call
sites, exact body line 3026 (zero-based), line count, helper/call hashes and 902
records. Rebasing only the outer source hash cannot admit modified probes.

The isolated test-only harness inverse restores collections866 before the
existing NStr→TextDocument→UUID→ValueTree→preprocessor history. No old source
becomes live-admissible, and no native fixture, old output, capture metadata,
workflow, runtime file or security boundary is edited. All eight Map-order
exception ordinals and labels remain unchanged; **every new record, including
any permutation of result IDs, is byte-exact**.

Runtime inventory remains 63, staged inputs 24, scenarios/artifacts 6. Caps remain
8192-byte finite stage report and32768-byte public summary, with unchanged output
and transport limits. Complete production serializer matrices were rerun for this candidate: 47 tests
passed, including all success/failure/async partitions. Strict finite maxima are
8185 / 8192 wire bytes and 32531 / 32768 public-summary bytes (7 and 237 bytes
remaining). These are full serializer bounds, not partial payload estimates.

## Acceptance and deliberately deferred work

Local instrumentation tests use explicit stubs which return known input nodes
independently of the filter. They test the observer and argument routing; they
are not search algorithms or native evidence. Existing runtime does not implement
FindRows. Local `action-error` outputs are not golden native answers.

Before any runtime implementation: update to the then-current integrated main,
obtain authorized genuine server/client capture, audit exact provenance/output
bytes, and decide coverage for every accepted native input. Comparison failure
remains failure, never successful measurement acceptance. No Find/Copy/Sort,
indexes, codecs, transport, detached-row lifetime, cap increases or broadened
source admission are part of this slice.
