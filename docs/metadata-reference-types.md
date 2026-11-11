# Snapshot-bound reference TypeDescription

Read-only metadata can describe a catalog or document reference using the actual
`Type` bound to the current interpreter's metadata snapshot. This adds no SQL
schema, query source, persistence operation or reference serialization format.

## Admitted API

```bsl
Types = New Array;
Types.Add(Type("CatalogRef.Categories"));
Description = New TypeDescription(Types);
Reference = Catalogs.Categories.EmptyRef();

Description.ContainsType(TypeOf(Reference)); // True
Description.Types();                        // a fresh Array containing that Type
Description.AdjustValue(Reference);          // the same reference value
Copy = New TypeDescription(Description);
```

`ОписаниеТипов`, `Типы`, `СодержитТип` and `ПривестиЗначение` are the corresponding
Russian names. The same singleton construction works with a bound
`Type("DocumentRef.Orders")`. Names in the examples must exist in the current
configuration. A bare `New TypeDescription("CatalogRef.Categories")` still has no
metadata lookup context and is not admitted.

The constructor accepts an exact built-in Array containing exactly one catalog
or document **reference** Type. A simple descriptor copy without additional
arguments is also supported. The descriptor keeps the original bound Type;
`Types()` returns independent mutable Arrays without cloning that Type. The
normal descriptor and qualifier properties remain immutable, with default scalar
qualifiers and the existing five-field descriptor shape.

`ContainsType()` compares metadata family, metadata UUID and **snapshot identity**.
A type from another catalog/document or interpreter is not contained, even when
its display name or database matches. A valid manager/object/selection Type is a
nonmember, not an implicit reference alias. Arbitrary host classes and subclasses
are not accepted.

`AdjustValue()` admits only an already matching exact catalog/document reference,
including a pre-existing empty reference. It returns that same object, retaining
its metadata and owner callbacks without invoking them. Other snapshots are
rejected rather than rebound. Scalar descriptors still cannot adjust references.

## Deliberately closed boundaries

- Omitted/Undefined defaults and conversion from Null, String, UUID, scalar,
  foreign family or foreign snapshot are not inferred. In particular, this code
  does not fabricate an empty reference without its metadata/owner callbacks.
- Reference unions, duplicate/mixed type arrays, Undefined mixtures, copy
  add/remove operations and qualifier overloads remain unsupported pending a
  separate contract. Only the narrow matching-value rule is implemented.
- Generic internal streams, JSON/XML codecs and ValueStorage reject these
  metadata-bound descriptors and reference values, also when nested.
- Typed reference ValueTable/ValueTree columns cannot synthesize a default, so
  column creation remains refused. Host-injected reference schemas do not bypass
  internal serialization, ValueStorage or external Query scalar admission.
- Query reference projections remain cursor-only. Their Unload and nullable
  reference schemas are not enabled by this descriptor support.

Existing limits are unchanged: 4,096 array type entries are inspected at most,
reference descriptions require one entry, and metadata Type names retain their
existing 256-character bound. Snapshot objects are opaque identities: equality,
hashing, iteration and lookup hooks on them are never invoked. Reference type
fields and default qualifier state are validated before comparison or copying.

## Metadata adapter integration

The internal `_reference_description(bound_kind)` convenience factory accepts an
existing `manager._value_type`. The metadata adapter must obtain that manager
from its own bound catalog/document collection. It must not reconstruct a Type
from a metadata UUID or borrow another interpreter's factory. This is the same
rule for user reference attributes and the standard `Ref` attribute.

Descriptors do not acquire a database reader or widen the authority of a
snapshot. Closing, replacing or refreshing a database remains the responsibility
of the existing metadata/application lifecycle, not `TypeDescription`.

## Evidence boundary

The official Syntax Assistant documents the Array(Type) constructor, including a
`CatalogRef` example, and defines `AdjustValue` to return an already matching
value unchanged. `Types` and `ContainsType` are ordinary introspection methods.
The bounded singleton implementation follows those documented cases. It does
not claim newly measured native conversion, default, ordering or codec parity.

Reviewed Syntax Assistant members under
`SyntaxHelperContext/objects/catalog63/catalog316/TypeDescription/`:

- `ctors/ctor19.html`: types and qualifiers constructor;
- `ctors/ctor15.html`: descriptor-based constructor;
- `methods/Types782.html`;
- `methods/ContainsType783.html`;
- `methods/AdjustValue1221.html`.

Focused tests are in `tests/test_metadata_type_descriptions.py`; existing scalar,
query, codec and storage checkpoints remain separate.
