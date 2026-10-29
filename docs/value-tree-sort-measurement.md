# ValueTree Rows.Sort: standalone measurement candidate

This is an **observer preparation**, not a runtime implementation or native
measurement result. It is deliberately not registered in profiles, staging,
workflows, shared fixtures or the full native suite. Nothing here establishes
Tree collation or stability from ValueTable/ValueList observations.

## API and boundary

The primary EDT 8.3 SyntaxHelper `ValueTreeRowCollection.Sort` (`Sort680.html`)
describes required String SortingLine, optional Boolean IncludeSubordinates
(default False), and optional CompareValues. EN `Sort` and RU `Сортировать` are
measured separately. CompareValues has a parameterless native constructor but
is absent from this runtime. A genuine comparator instance is therefore a
**future new-type dependency**, not an initial waived failing case. Omitted,
explicit Undefined and invalid numeric comparator arguments remain measured.
No strings are sorted: Key/Secondary are small numbers; Tag only identifies rows.

## Fresh cases

Every case constructs its own tree; nothing clears/reuses a prior receiver.
The normal fixture has three untyped columns `Key`, `Secondary`, `Tag`, two
roots, two children per root, and two grandchildren under the first child of
the first root. Preorder tags are `a` through `h`; Key is `22211111`, Secondary
`11122112`. Thus root order, child order, recursive grandchild order, and
secondary-key tie ordering can be distinguished. Cases 8/9 instead construct
18 flat rows tagged `a` through `r`, Key `2-(index%3)` and Secondary
`2-(index%2)`. The duplicate-key size intentionally exposes competing stable
and unstable models; neither answer is assumed to be native Tree behavior.

| Case | Operation |
|---|---|
| 1 | root EN `Sort("Key")`, positive default control |
| 2 | root RU `Сортировать("Key", False)`, positive explicit-False control |
| 3 | root Key, True |
| 4 | first root's child receiver Key, True |
| 5 | same child receiver, default recursion |
| 6 | root `Key ASC, Secondary DESC`, True |
| 7 | root RU `Key Возр, Secondary Убыв`, True |
| 8, 9 | 18 duplicate-key roots, Key ASC / DESC |
| 10 | empty tree with schema, Key |
| 11–13 | Missing / Key, Missing / Missing, Key |
| 14 | empty selector |
| 15 | missing required argument |
| 16 | fourth argument |
| 17 | numeric selector |
| 18 | Array recursion argument |
| 19 | explicit Undefined comparator |
| 20 | invalid numeric comparator |
| 21 | procedure used as expression, dynamically executed |

## Observer and wire contract

`integrational_tests/measurements/tree_sort.bsl` emits independent `TS-C1`
calibration followed by exactly 21 `TS-n` records. Calibration verifies primitive
encoding, tree/columns/column/row equality controls, hierarchy, and repeatable
snapshots. **Rows wrappers are never registered as identities**: native repeated
Rows access is not assumed equal. Root and child Rows labels refer explicitly
to their structural tree/row owner; each Rows.Parent is separately checked.

Each case retains one real-object registry across its entire before/after
snapshot pair. A snapshot records tree and column-collection identity, all column
identities/name/title/width/type and qualifiers, preorder real row IDs, Parent,
Owner(), Level(), structural child-Rows owner, child count, and every cell.
Cells retain type (numeric, string, Boolean, Undefined, Null), not merely text.
Finite encoding domains match the fixtures; unrepresentable changes are observer
failures, never silently normalized or omitted. Bounded corruption within the
domains is preserved, not checked against a guessed native answer.

Action outcomes `S/M/A/O` mean success / recognized missing method / recognized
argument diagnostic / other action error. These coarse categories are not a
claim of language-independent native error taxonomy. The handler captures
`OriginalErrorDescription = ОписаниеОшибки()` before invoking any helper.
After **every** action, including errors, the whole tree is observed again, so
partial mutation is not discarded. Observer failures `XB/XO` remain separate
and invalidate the capture. No raw error text is emitted.

`scripts/native_1c_tree_sort_contract.py` validates exact ASCII, ordered framing,
fixed finite field grammars, canonical identity allocation/kinds and case bounds.
It does not enforce assumed native sort results. `validate_output()` can parse
an all-missing-method capture; **`require_available()` additionally requires
successful EN and RU positive controls**, so missing Sort cannot produce green
availability. Availability alone is not native parity or feature completeness.

## Constructive budgets and current integration risk

The largest accepted full records are constructed and decoded by the focused
contract tests, not estimated from source length:

- snapshot: `5 + 13*columns + nodes*(6 + 2*columns)` ASCII bytes;
- 18 normal cases, two 18-row cases and one empty case, each before/after;
- calibration plus all 21 maximum framed records: **6,443 bytes**, under the
  unchanged **8,192-byte** capture cap (1,749 spare bytes);
- the existing tree harness uses a **separate completed JSON marker**, not an
  invented output success suffix. A proposed `tree-sort-v1` marker with these
  values is 6,605 compact bytes; charging BOM, separator spaces and optional
  escaping of every slash yields **6,702 < 16,384**. This is a constructive
  planning proof, not a registered profile or a real client marker.

Before future integration, `full_suite.py` on this base is 289,493 LF bytes and
294,075 CRLF bytes: **only 837 bytes below its 294,912-byte bound**. Keep large
logic outside it; remeasure staged bytes and module budgets after integration.
Do not increase capture or staging caps to fit this shard.

## Verification and next gate

Focused tests run normally and with `python -O`. Synthetic HostFunction models
separately exercise missing method, no-op, stable/unstable ties, receiver-only
versus recursive sorting, child receivers, multikey EN/RU, procedure-expression
failure, invalid arguments, and mutation followed by an action error. Tests also
inject observer corruption, check real identities and schema/row metadata, and
prove malformed output cannot become a success. These are **synthetic observer
checks, not native answers**.

Next: independently review this standalone source/decoder, then separately
integrate bounded capture/profile handling, acquire real 1C EN/RU observations,
validate availability and every record, and only then select bounded runtime
semantics. Native comparator instances, mixed-type ordering, collation, UI and
unbounded trees remain outside this shard. Existing six ordinary sources and
Fill/Copy measurement BSL/contracts must stay byte-identical in this preparation.

## Subsequent local integration

The description above records the reviewed standalone preparation. The separate
[fixed-profile integration](value-tree-sort-profile.md) now supplies registry,
server/client acquisition and acceptance wiring; native acquisition is still
pending. No runtime Sort implementation or native answer is implied.
