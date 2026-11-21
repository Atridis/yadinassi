# Exact direct Map operator identity

`New Map` uses an exact `_TypedMap` in the direct backend. Its inherited Python
dict comparison incorrectly made separate maps with equal contents compare equal.
The existing `test_maps_and_other_collections_have_identity_equality_not_deep_equality`
exposes that mismatch independently of the previously repaired Array/Structure
operators.

The new explicit `map_identity_equality` repair uses identity for `=` and `<>`
when either operand is an exact `_TypedMap`. Payloads, keys and mixed foreign
operands are not compared, traversed or hashed. Existing exact Date boundary
rejection still happens before the identity shortcut. Both operands are evaluated
once, left to right. Other pairs retain separate Python `==` and `!=` behavior.
Raw dictionaries, `_NakedMap`, subclasses and fixed-map internals are not newly
reinterpreted. Primitive-literal exclusion remains unchanged.

This is an independent repair flag, enabled in the direct backend. A helper pair
is selected at preparation time according to the Array/Structure flags; all eight
flag combinations have explicit tests. Profiles without the Map repair keep
their previous helper selection. Map key equivalence, typed-key hashing, Find,
copying, constructor admission and public receiver capabilities are unchanged.
No VM evaluator or legacy fallback is involved.

Map-specific evidence, not an inference from Structure: the frozen native
collections records `internal.map.independent-equal.restored-pair-equal` and
`internal.map.repeated-reference.restored-pair-equal` are both false. Tests retain
those observations and separately compare direct versus canonical runtime for
self, alias, equal contents, cyclic values and copy identity. This does not claim
a new native capture or extend the observation to every collection type.

Security regressions cover hostile payload equality/ne, mixed host operands,
cyclic maps and Date boundaries; route tests cover source/AST/prepared/Eval/Execute
with legacy dispatch poisoned. Existing typed scalar keys and equal-looking map
keys remain distinct where required. No performance improvement or full native
parity is claimed.
