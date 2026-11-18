# ValueTable storage/schema simplification: contract before implementation

## Existing contracts, not inferred cache permissions

`tests/test_value_tables.py` replays owner checkpoint behavior: case-insensitive
name lookup and duplicate-name rejection; empty names; retained column identity
across rename and move; deleted descriptors cleared; deleting the last column
clears rows. Index tests preserve column identity and indexed write ordering.
Anonymous columns can duplicate the empty name: a name map must retain the first
physical match, and Move must update it. A simple name-to-last-column dict would
be wrong.

Raw Python access is genuinely used:

* `query_reference_tables.py:154` appends constructed columns directly.
* `test_value_table_sort.py:226` replaces `.items` with a list subclass and counts
  iteration; it is not lawful to silently snapshot and disregard that object.
* `test_value_table_index_codecs.py:268` removes a referenced column directly,
  expecting corruption detection, not a stale successful lookup.
* Column `.name` is a directly stored attribute. Changing it is not currently
  forced through the BSL `set_member` path.

Therefore an epoch incremented only in existing BSL methods is not a correct
invalidation scheme. Python name/list mutation must remain visible or be rejected
explicitly under a documented API change. No silent stale cache is acceptable.

## Proposed coherent storage boundary

1. A schema-owned ordered column registry maintains exact column identities and
   a casefold name index. It is authoritative storage, not a cached conclusion
   over an independently mutable list. Anonymous duplicates preserve first-match
   physical order. Column rename and all structural operations publish both
   representations atomically after duplicate/type/owner preflight.
2. Public collection operations use that registry. A compatibility entry point
   for raw Python storage replacement enters an explicit untracked representation:
   lookup uses the live storage and retains existing validation. It must never
   claim an epoch is proof of unobservable mutations. Imported canonical schemas
   instead use a dedicated validated bulk construction path.
3. Shared row storage primitives implement append, index addressing and cell
   mutation. Internal append receives no user index and does no Decimal roundtrip.
   User Insert/Get retain BSL conversion and error-order semantics. The untyped,
   unindexed append primitive is the same one used by an admitted direct region,
   rather than maintaining two independent row implementations.
4. Optional index observers preflight affected keys before mutation and preserve
   native remove/reinsert ordering even for equality-preserving indexed writes.
   No-index storage does not create empty key plans or perform empty unit sums.
5. Typed defaults remain live per schema/qualifier contract. Do not memoize a
   default merely because the type-description object has unchanged identity.

## Admission and compatibility gates

Existing direct regions inspect exact class dictionaries, object dictionaries,
list layouts and helper identities. Registry/property changes require explicit
updates to those contracts and independent hostile descriptor/metaclass, stale
row, foreign column, codec and post-callback re-admission tests. They are not
justified by class microbenchmarks. Unknown host mutation stays outside the
canonical optimized representation; it must not become a VM fallback.

Migration gates: native rename/anonymous/move/delete fixtures; retained row and
column references; raw direct append/replacement/mutation compatibility; codec
roundtrips and deliberately corrupt registries; typed qualifiers; indexed
failure atomicity; class/AST result parity; width-sensitive build/lookup wall
measurements (1/16/256 columns) with separate raw lower-bound comparisons.

This design removes schema rescans, internal conversion roundtrips and absent
index planning as one storage responsibility split. It does not remove owner,
revocation, type or transaction checks, and is not yet implemented.
