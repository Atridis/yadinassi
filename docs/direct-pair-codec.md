# Direct iterator-pair internal serialization

Direct `For Each` emits detached `_MapEntry` snapshots. The direct internal
serializer now recognizes only the retained exact definition type, reads its
original storage descriptor without executing instance/class attribute hooks,
and requires precisely the `key` and `value` fields before visiting either.
Subclasses and foreign values receive no new admission. Public `_MapEntry`
rebinding does not change this domain. These snapshots have no owner, disposal
or lease; the service invocation still checks the active boundary and policy,
including after argument evaluation and when a callable has been retained.

The existing native-backed KEY_AND_VALUE wire codec is reused. The committed
1C records `internal.key-and-value.structure` and `.map` establish the scalar
payload and readback shape; tests compare exact payloads and read back the
canonical pair type and both fields. No native records are modified. This is
not new evidence about arbitrary host objects, cycles or resource limits.

Existing writer depth, node and output-byte budgets and active-path cycle
checks also cover nested direct pairs. Repeated acyclic aliases remain legal.
Malformed storage and unsupported payloads fail without reflection/coercion.
There is no external write or persistence operation. Captured canonical
serialization gains only this exact pair case; all its other inputs retain the
previous canonical behavior. Custom registered functions remain custom.
No equality, hash, collection lookup or iteration semantics change.
