# Standalone direct ValueTree bridge

This slice adds the canonical `ValueTree`/`ДеревоЗначений` constructor and
exact ValueTree, row, row-collection, column and column-collection receivers to
standalone direct execution. Source, AST and prepared execution use the same
bridge, including standalone imports and Eval/Execute. It does not enable
source/configuration authority or add a server constructor route. Child tree
types have no public constructor. There is no VM fallback or arbitrary host
factory/receiver grant.

## Authority and dispatch

The model records weak birth links at canonical construction and public Copy.
The bridge checks exact receiver types, definition-time class/base hooks,
instance field shapes, live root/ancestor links, current limits and boundary
activation. Fabricated objects, subclasses and coherent reparenting do not
acquire authority. Method calls recheck after argument evaluation; retained
method closures also retain an activation epoch, not a reusable grant.

Local Count/read/Add checkpoints do not traverse unrelated rows. Operations
that can traverse or mutate a whole graph use the existing bounded graph
preflight. Column metadata is checked for operations that access it. This is
not a performance claim: scoped checks still have class, column and ancestor
costs. Public deleted-column and forwarded row-collection behavior remains in
the existing model implementation.

Definition-time empty copyreg slot caches prevent ordinary copy/deepcopy from
changing the sealed class ABI. Cache contents are checked on every bridge
entry. Host copies of complete object graphs are not automatically admitted
as canonical birth graphs; the public ValueTree Copy operation records its new
rows explicitly.

Only two native collection adapters are added: exact direct lists for
LoadColumn and exact direct structures for FindRows. They use checked shallow
canonical views without changing element identity. Other collection conversion
or generic iterable support is not implied.

## Verification at this checkpoint

The new adversarial module and existing `test_value_trees`,
`test_value_tree_columns_clear`, `test_value_tree_columns_delete` and
`test_value_tree_columns_move` run 83 tests successfully in both normal and
optimized Python 3.12. Coverage includes no-VM source/AST/prepared execution,
late argument hook changes, foreign/fabricated receivers, parent revocation,
expired activations, source-scope exclusion, copy bookkeeping and the absence
of full-graph scans in repeated local Add/Count.

A separate 117-test copy/find/findrows/load/unload/move/sort/total cohort has
115 passes and two unresolved failures:

* `CopyNativeCaptureTests.test_actual_unpatched_runtime_matches_exact_source_bound_native_main`
* `CopyNativeSemanticsTests.test_shared_outer_nested_arrays_and_alias_groups`

These involve native array alias/equality output. The exact parent fails earlier
on missing direct ValueTree support; the legacy backend passes these cases.
The direct compiler still compares native lists structurally rather than by
identity. Original semantic assertions are unchanged. An
additional native replay run was interrupted and is not counted as validation.
No full-suite, native 1C parity or performance result is claimed here.

## Follow-up scoped-guard review

Column Add/Insert now preflight the graph before walking the row registry.
Row-cell dictionaries are checked for exact same-root canonical column keys
before lookups, without hashing or comparing foreign keys. Schema descriptions
and qualifier hooks/fields are checked before defaults or coercion; row depths
are checked against their parent. Retained setters, references and iterators
cannot revive in a subsequent activation. Collection Get/iteration requires
exact row/column results while row-cell payloads remain ordinary values.
Six additional adversarial tests cover these cases; the separate 117-test
cohort still has exactly the two failures listed above.

## Private identity row registry

The mutable object-key `_all_rows` dictionary has been replaced by an exact
private wrapper with no instance backing-storage attribute. A module-private
sidecar stores integer identities and weak row references, bound to a weak root
and the wrapper identity. Tree birth provenance includes the registry identity.
Foreign keys and non-None values are rejected before hashing, equality or
formatting. Raw dictionaries and other roots' registries cannot replace the
canonical registry at a direct boundary.

Valid rows remain strongly owned by their row collections. Weak sidecar values
avoid a global sidecar-to-row-to-tree retention cycle. A dead row reference sets
a private corruption flag; it is not silently pruned. Length/insertion checks
are constant-time in the number of rows. Native Delete/Clear remove entries
explicitly, so ordinary row removal does not corrupt the registry. A retained
registry whose root has died refuses access. This deliberately differs from an
old corrupted dict that alone retained an otherwise unreachable row.

Iteration order, items, mapping conversion, pop, clear and snapshot comparison
remain available for model-internal callers. Existing invalid-registry tests
still assert rejection by the same native operation; two fixtures now inject a
raw dictionary into the root field because invalid-value insertion is refused
by the wrapper itself. No semantic expected output was relaxed.

The new tests cover GC of a whole tree, a retained orphan wrapper, a dead-entry
corrupt graph, ordinary removed-row GC, foreign hash/eq/repr callbacks, registry
class hooks, root swaps and public Copy. A deterministic operation-counter test
checks that 20 local Add/Count iterations perform exactly twice the registry
checks of 10 iterations, without invoking registry iteration. This is a
complexity regression, not a wall-clock performance claim.

Definition-time dependency guards additionally cover Enum hooks/MRO,
TypeDescription/qualifier bindings, output Array construction and Date/UUID
scalar hooks. A subprocess checks that a pre-lazy-import Date constructor patch
is not admitted. Canonical copyreg bookkeeping on scalar classes is allowed
only for the exact expected slot-name list.

Final focused normal/optimized result: 83 tests pass. The 117-test cohort still
has the two unchanged failures above. The additional 65-test property-transfer
module has three errors and one failure; an exact 407d12e2 parent checkout has
the same four failing methods. These are not claimed as passing, and these earlier focused checks alone were not broad-suite acceptance.

Canonical Enum members also have definition-time field-identity snapshots.
These are checked after the class ABI but before hashing or defaults, including
all field-key types before any dictionary lookup. Forged exact-class members
are not accepted as descriptor/qualifier values. Regressions cover hostile
`_name_`/`_value_`, foreign colliding field keys, all four Enum families and a
pre-lazy-import member patch in a subprocess (normal and optimized Python).

## Integrated compatibility verification

On parent `feb824c0f758e80f64b51ae85d7c8edbfa72401c`, all 278 existing
ValueTree and property-transfer tests pass with explicit `compiled-strict`.
The same cohort with the unchanged default direct backend has 162 errors and
four failures. With this bridge and private registry, it has 17 errors and
seven failures: 41 formerly failing methods now pass, with no new failing
method identities. More tests reach their semantic assertions instead of
stopping at an unsupported constructor. These numbers are not native parity.

Remaining direct issues include legacy `.items` test representation assumptions,
TypeOf coverage in large mixed fixtures, Array identity equality, LoadColumn and
Move output differences, and existing property-transfer admission/omission
gaps. None of those expectations has been weakened. The final Enum-state
hardening additionally passes 2,058 broad direct/source tests both normally and
with `-O`; the integration retains all earlier guards and source exclusions.
The registry's deterministic linear-growth regression is not a speed benchmark.

The final integrated production tree was checked again after integration on
`5e2576a2e3b2d5cc648dbe643d02007f4dbff183`: 2,058 broad tests pass normally
and with `-O`, and all 278 existing ValueTree/property-transfer tests pass with
explicit `compiled-strict`, including unchanged source-bound native fixture
assertions. This proves preservation of that legacy cohort, not direct native
parity. Direct residuals listed above remain visible and are not skipped.
