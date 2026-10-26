# ValueTree Rows.FindRows — bounded native-backed alignment

## Evidence, not a fresh acceptance result

[PR119 initial native run 40283979870](https://github.com/Atridis/yadinassi/actions/runs/40283979870)
executed head `39f59c076bcfbf4d594b4f51ef363f579f9a489e` through merge
`4d67ef8b5dec7b07f8c01325c107d6d0ad6363bc`, tree
`b99576697424054b7a2944860d8d43602e78dd01`, on Linux 1C 8.3.27.1508.
Its authenticated server and managed-thick-client collections outputs agreed
on all 902 records. The 36 new observations contain 27 successes and nine
query errors, with no setup/change/observer failures. The original interpreter
had no method implementation: it disagreed on the 27 successes. That run's
final verdict was **failure**, not interpreter acceptance or full138 success.
No discarded optional preprocessor/infobase tokens are reconstructed.

The exact 8881-byte new native tail has SHA-256
`ff0e72138da5f1e41a4853f7fe797acc9e82a2f8e4ff792704bb6eca219402e3`.
All 36 literal records are retained in `tests/test_value_tree_findrows_native.py`,
independently of the runtime model. Replaying those bytes is not a fresh native
execution. Fresh updated-head CI/native acceptance remains required.

## Implemented measured model

Only `ValueTreeRowCollection.FindRows` / `Строки.НайтиСтроки` is added:
`rows.FindRows(filter, recursive=False)`. The method is not on a tree or row.
The filter must be a mutable Structure, not FixedStructure. All names resolve
against the shared tree schema, case-insensitively, before an empty receiver
can return. Unknown columns fail even for a leaf's empty child collection.
All predicates are conjunctive; their order does not reorder the result.
An empty Structure returns a fresh empty Array, not every row.

False and an omitted second argument search only immediate children. True
performs preorder depth-first traversal, visiting descendants of nonmatching
parents too; the receiving collection's parent row is excluded. Native creation
order `A,B,B1,A1,A2,A11` returned IDs `1,4,6,5,2,3`, not insertion order or BFS.
The implementation walks hierarchy lists iteratively using iterator frames;
`_all_rows` is not used as a search traversal or index.

The initial matching domain is String, Number, Boolean, Undefined and Null.
Types remain distinct (Number 1 is not True), strings retain case and trailing
spaces, and Undefined differs from Null. Generic bounded values in these scalar
families use the existing typed equality helper; neither runtime operator
Number/Boolean coercion nor ValueTable indexes/typed-cell adjustment is used.
Representative native witnesses support this model, not every numeric/Unicode
edge. Date, UUID, Type/TypeDescription, collections and arbitrary objects are
currently unsupported search values, even though some have separately evidenced
scalar equality elsewhere. Their storage in untyped cells is unchanged.

The returned mutable Array owns its membership/order list and shares the actual
row objects. Mutation in either direction is visible through both references.
Array deletion does not delete a tree row. A later tree addition or changed
filter affects a new query, not a saved result. No lazy view, copy of rows or
retained filter is created.

## Recursion conversion: observed cases versus local extension

FindRows directly measured Boolean True/False, omitted False, Number **1**, and
exact String **`"True"`**. Both formerly suspected invalid Number/String cases
are supported; neither is dropped or waived. Explicit Undefined is rejected.

The existing bounded TypeDescription Boolean converter is reused only after
identity-based exact-type gates and explicit Undefined/Null rejection.
TypeDescription itself maps Undefined to False, so its default cannot leak into
FindRows. Host objects and primitive subclasses cannot spoof a gate with
metaclass equality or invoke conversion/equality hooks.

All bounded finite Decimal recursion arguments follow nonzero→True, zero→False
as an **explicit local compositional extension**, not a measured native
FindRows-wide coercion rule. The separate unchanged `values.bsl` checkpoint
`types.adjust.boolean.text/zero/number/undefined` observed TypeDescription
conversion of `"True"`, 0, 2 and Undefined. That evidence supports the converter,
not applying every converter input to this method. Negative/fractional Decimal
flags are algorithmic local policy. String `"False"`, lowercase/Russian forms,
whitespace, numeric strings, Null and objects remain rejected.

## Safety and local resource policy

Existing whole-tree limits remain: 100,000 rows, 4096 columns, 1,000,000 cells,
maximum row level 256. A search additionally bounds visited rows/selected cells
and iterator depth. Per-string search content is at most 1,000,000 characters;
Numbers must be finite with at most 4096 coefficient digits. Before coefficient
inspection, a conservative 3 × 4096-unit reservation protects a bounded Decimal
context precheck and the existing converter/tuple extraction; unused units are
refunded to three units per actual digit. Calls with insufficient reservation
headroom fail early even if the eventual coefficient would be short. Oversized
coefficients (including trailing zeros) fail before an unbounded Python digits
tuple can be allocated. The temporary context shifts only its validation value,
so extreme stored exponents do not underflow; original values and ambient Decimal
flags/traps remain unchanged. The recursion converter is charged separately.
No exponent-sized string expansion, encoding, recursion or column adjustment occurs.

An 8,000,000 logical-work budget charges schema/filter names before casefold
and normalized-key lookup, query content, visited rows, and both operands before
comparison. Repeated comparisons spend repeated content units. These are
Yadinassi limits, **not native maxima**, and do not raise an existing limit.
All selected cells of a visited row are validated and charged before conjunction
short-circuiting, so a false first predicate cannot hide an unsupported object.
Unselected columns are not inspected. Resource/type failures return no partial
result and never mutate the tree, filter, or older result arrays.

Deleted child collections and rows remain invalid under existing tree lifetime
policy; a saved result does not resurrect a removed row. The new probes did not
measure deleted-result-row lifetime. Earlier native retained-grandchild rejection
is narrower evidence, not full detached-row compatibility. Precedence between
multiple invalid arguments, unsupported data behind an otherwise false predicate,
resource bounds and host-corruption rejection are local safety policy, not native
exception-class/message claims. No new trailing-comma-hole syntax is admitted.

## Unchanged boundaries and tests

The 4241-line/327655-byte collections source remains SHA-256
`5468d16850a9774251d4ef80ae5e938afdfabef69fe496cb3a6cb579d0564782`.
All 36 probes, collections902, the exact historical source inverses and old raw
fixtures are unchanged. Exactly eight historical Map-order exception labels and
ordinals remain; every new record and result-ID permutation stays byte-strict.
No Find/Copy/Sort, index, codec, transport, admission, workflow or security change
is included. The production change stays in `value_trees.py`; runtime inventory
remains63 and staged inputs24. These counts are identities, not architectural
maximums. Finite serializer caps stay8192/32768; exact runtime content provenance
is recomputed for the candidate, not reused from the failed measurement run.

Native-literal replay is separate from `tests/test_value_tree_findrows.py` generic
model and local-policy tests. Those test reference identity, non-creation DFS,
nonmatching ancestors, unknown schema on empty receivers, hostile metaclasses,
primitive subclasses, unsupported selected cells, failed-call atomicity, deep
iteration, and patched boundary budgets. Packaged smoke also exercises recursive
order, local default, numeric/string flags, shared rows and observed errors.
