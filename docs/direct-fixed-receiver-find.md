# Direct FixedArray.Find: mutable direct collection identity

`FixedArray.Find` reused canonical `values.equal`, which received the direct
Structure/Map dict representations. Separate equal-content objects therefore
matched through Python dictionary equality. Mutable direct Array.Find already
used identity; the fixed receiver was inconsistent with the existing canonical
`test_array_find_keeps_mutable_structure_and_map_identity_behavior` contract.

A narrow direct adapter now scans the exact canonical FixedArray tuple by `is`
when the needle is an exact direct Structure or typed Map. It preserves first
index, Decimal result, aliasing and misses; it neither traverses nor compares
payloads, including cycles and foreign elements. Canonical named and captured
Find methods share this path. No new receivers, constructors or member methods
are granted. Receiver/storage ABI, boundary lifetime and captured metadata are
checked before and after dispatch, including after argument evaluation and policy.

Other needles retain the previous canonical Find implementation and its existing
trusted-host equality semantics. This is not a general sandbox replacement for
canonical Find. Subclass/foreign methods do not enter the new adapter. Direct
collection operator equality, map keys, mutable Array.Find, fixed construction
and snapshot semantics are unchanged; no VM/legacy fallback is introduced.

## Evidence limits

The existing native collection capture's `fixed-array.find: [0]` covers a scalar
needle. `fixed-*.find-alias/find-copy` use a mutable Array receiver with fixed
needles, not this combination. No archived native observation was found for a
fixed receiver with mutable Structure/Map needles. This is a canonical-consistency
repair, not a claim of newly measured native parity. Tests separately compare
compiled-strict controls and preserve the existing scalar native observation.
