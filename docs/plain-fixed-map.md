# FixedMap snapshots of native direct maps

Exact PlainMap construction now takes one native `dict.copy` and wraps it in a
MappingProxyType held by an exact PlainFixedMap. No nested traversal, conversion,
key-token wrapping or second dictionary copy occurs. New Map(snapshot) makes an
independent outer native mapping; nested values retain identity.

The source's supported scalar-key mutation API supplies the invariant. There is
no extra Python key scan in this ordinary constructor. Raw host edits that
bypass PlainMap's scalar-key API are outside that existing storage contract;
this does not admit arbitrary mappings or host-provided mapping proxies.
Lookup keys still pass the same exact scalar-domain check before hashing.

Get, strict missing-key index reads, Count, foreach, String, TypeOf, identity
comparison and read-only rejection use finite direct routes. Native Python key
collisions (e.g. True and Decimal(1)) remain those of PlainMap. Canonical BSLMap
inputs still produce canonical BSLFixedMap with their existing typed-key rules.
Legacy classes and their token-shaped storage are unchanged.

JSON writing reads the exact native dictionary retained by the FixedMap
snapshot. It does not call the map's iterator or the mapping proxy's methods.
JSON property names must still be strings. Other serializers and session
parameters that require the canonical `_items` shape remain unchanged.

Focused checks cover execute/prepared, shallow identity, source detachment,
reverse copy, scalar-key rejection, legacy key rules, and immutable access.
Nine focused tests passed normal/-O. Existing fixed/ref cohorts are not green:
76 tests had 66 errors on baseline70f17ec; the initial candidate reached deeper
checks with 43 errors and 2 failures. Old Python-class identity and object-key
expectations do not describe the native PlainMap route. No broad compatibility
claim is made.

Small construction-only timing (median5×1000, no full runtime/preparation):
512 entries raw proxy(copy)1.780µs, PlainFixedMap2.260µs (1.270×);
4096 entries15.135µs vs15.326µs (1.013×). These are isolated microbenchmarks,
not end-to-end speed guarantees.
