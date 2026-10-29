# ValueTree.Copy: native-backed bounded runtime

## Evidence and current status

[Native run 40926194836](https://github.com/Atridis/yadinassi/actions/runs/40926194836),
attempt 1, head `08982c9751e03d496fa3d4b2e4d45e0900a15cfc`, authenticated the
source-bound server and managed-client Copy captures, provenance and cleanup.
Both sites produced the same full capture: 6269 bytes, SHA256
`dae222dc6fe669bedadc51cb6e8ffde4e2707559c8d44f9fb7ed8aaab533112c`.
The independent nine-case main projection is 6237 bytes, SHA256
`2350822aa712702e7f3ac31020a71307421dddcb6b4d5d9ed49c0eabd07c2238`.
The original run correctly reported runtime parity false: Copy was then absent.
That receipt is not relabelled as a runtime pass.

The genuine bytes and minimal public provenance are committed under
`tests/fixtures/value_tree_copy_linux_8_3_27_1508.{out,json}`. The `.out` is pinned
byte-exact on all checkouts. The unpatched runtime now reproduces the main bytes;
separate focused/full/production and fresh exact-head CI/native gates remain
required before merge. This document does not claim those future gates passed.

## Measured semantics

`ValueTree.Copy()` / `ДеревоЗначений.Скопировать()` takes no arguments. Cases1–8
succeeded; English `Copy(1)` failed with an argument error and left the source
unchanged. Both aliases dispatch to the same local zero-argument implementation.

The result has new tree, Columns collection, column and row objects. Current
schema order, names/titles/widths/type descriptions, preorder hierarchy, sibling
order and values are preserved. Parent, Owner and Level refer to the new structure.
Scalar cell-slot assignments, row add/delete and column metadata/add/delete are
independent in both directions. The measured schema includes untyped cells,
Number(6,2) and String(5); scalar cells include Number, String, Boolean, Null and
Undefined. This is not an exhaustive native qualifier/coercion matrix.

Cell references are shallow: the outer **and nested** Arrays in case7 keep their
identities across source/result. Shared cells remain shared, distinct equal-content
Arrays stay distinct, and outer/nested mutations propagate both ways. Therefore
Copy clones structure, not mutable cell contents. No `deepcopy` or cell conversion,
equality, iteration or serialization hooks are invoked. Opaque host cell references
are also retained locally without inspection; this safety invariant is not native
evidence for every arbitrary object kind or a new object-codec contract.

Native repeated Rows access compares unequal even when saved aliases compare
equal. Runtime Rows getter wrapper behavior is unchanged by Copy. The strict
[TC-C2 observer](value-tree-copy-profile.md) records explicit structural collection
owner labels instead of asserting wrapper identity. Its separate `TC-P` access
probe never participates in nine-case Copy parity; scalar probe controls must
still be valid. No native-only success bypass is added.

## Local implementation and limits

`yadinassi/value_trees.py` validates the complete source graph iteratively before
allocating the result. It checks exact internal collection/row/column shapes,
ownership, parent/depth links, live objects, unique membership, cell keys and the
whole-tree row registry. It then constructs new columns and rows in hierarchy
order, copying cell slots directly. Immutable TypeDescription/default-string
metadata can be shared; column objects themselves are independent. The source is
never modified, including on validation/allocation failure. Cycles, foreign keys,
duplicate rows and corrupt host-created graphs fail closed rather than invoking
foreign equality or cloning hooks.

Existing local caps remain 100000 rows, 4096 columns, 1000000 cells and depth256
(root depth0). Padded default text remains bounded to1000000 characters. Copy also
bounds combined names/titles/case-folded names to1000000 characters and uses the
existing bounded Decimal admission for column widths (4096 coefficient digits,
shared8000000-unit work budget) before arithmetic. These are Yadinassi resource
policies, not inferred native platform maxima. Valid multiple unnamed columns are
preserved, consistent with the existing column API. History/reordering, unnamed
columns, deep traversal and corrupt-graph tests supplement rather than expand the
bounded native measurement claims.

Sort, UI, XML/internal tree codecs, transport and arbitrary Copy parameters remain
outside this feature. `FillValues` remains a ValueTable method, not a tree method.
