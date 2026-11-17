# Bounded source XDTO flat scalar objects

The ordinary source application's global factory can return a current object
`Type` only when the **entire type** is flat: no base type, every declared property
is single-valued (upper bound 1, lower bound 0 or 1), and every property type is
one of the existing supported scalar primitives or direct scalar aliases.

`Create(T)` constructs such an object, reserving one node. Declared property
reads return the native scalar value (or Undefined for absent/nil values).
Direct property assignments accept primitive strings, booleans and numbers;
Undefined/Null are accepted only for nullable properties. Property spelling uses
the existing XDTO property's exact name. Conversion and quota checks precede
canonical mutation; rejected conversion or exhausted budget preserves the old
value and accounting. Repeated scalar assignments retain the existing cumulative
allocation semantics rather than refunding replaced values.

This is not selective access to a complex type. A type containing a nested object
or list remains unsupported even if one of its other properties is scalar. In
particular the native fixture's `Child.Label` is flat, while its `Record` and
linked `Envelope` remain outside this slice. No historical fixture is weakened
to make an IO test pass.

Only objects produced by this guarded global factory path are admitted. Private
application-owned canonical records pin object, descriptor, value-map and scalar
child identities. They do not trust a mutable marker on the value. Objects are
intentionally retained until application close, within the global factory's
cumulative node/unit limits; close releases the records. Records contain no
strong application backlink. Local empty factories retain their separate scalar
contract and cannot construct these source-package object types.

A setter binds and validates its property before the right-hand side runs, then
revalidates the object, descriptor, source owner, hooks and budget at invocation.
Saved activation-bound setters expire with their source boundary. Foreign,
forged, stale or closed ownership and mutated state fail closed.

Object methods, indexing, lists, nested objects, XML/JSON readers or writers,
Packages, schema loading and generic database receivers are not added. Scalar
Create(type, value) and the separate local-factory capability remain available.
There is no VM fallback and no new native-1C parity claim. These boundary guards
are not a sandbox against arbitrary replacement of the trusted Python runtime.
