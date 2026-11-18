# Direct iterator-pair TypeOf classification

Direct Map and Structure iteration creates the private exact `_MapEntry`
representation. Its public type is `KeyAndValue`, just as the legacy
`BSLKeyAndValue` representation. The canonical direct TypeOf service now maps
that definition-time retained exact class identity to `BSLType.KEY_AND_VALUE`.

The mapping neither reads nor converts key/value payloads. Subclasses and
lookalike objects do not qualify. This is type classification, not provenance
or ownership admission: it does not grant methods, indexing, mutation,
serialization, database access or generic receiver capabilities. The standalone
canonical `type_values.type_of` API remains unchanged. Registered custom
TypeOf implementations remain custom; canonical aliases keep canonical behavior.
Existing service policy, lifetime and post-argument function-identity guards
remain in effect. There is no VM fallback.

The reproduced source blocker is `TypeOf(Pair)` in the Map iteration section of
historical complete collection replays (LoadColumn replay line 3830). Admitting
this type does not claim that the rest of those historical scripts passes,
nor that current direct execution matches all native output bytes.

Validation on base `84273a41`: 16 focused tests pass in normal Python 3.12
and Python 3.10 `-O`. A bounded complete LoadColumn replay advances past
`TypeOf(Pair)` at line 3830 and stops at line 3841, an attempted iterator-pair
property write. The existing `BoundaryViolation: unregistered or foreign
database receiver` remains unchanged; this slice does not grant writes or turn
that boundary violation into a catchable language error. The complete replay
therefore still fails, and no full/native parity success is claimed.

Independent review caught a pre-lazy class-rebinding gap in the initial import.
The final implementation retains the class at its compiler definition, rather
than trusting the mutable `_MapEntry` name when services first load. A fresh
subprocess regression rejects the rebound counterfeit before lazy import and
still classifies the original pair.
