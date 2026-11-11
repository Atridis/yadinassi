# Read-only configuration metadata

`Metadata` / `Метаданные` describes the **currently admitted logical schema** of
an owned SQLite application. It is not a native binary configuration parser.
Configuration code is never executed by loading metadata.

## Supported graph

- Configuration `Name`, empty admitted `Synonym` / `Comment`.
- `Catalogs`, `Documents`, `InformationRegisters`, and the explicit
  `ConfigurationApplication`'s `CommonModules`.
- Catalog/document `Attributes`, `TabularSections` and their `Attributes`.
- Register `Dimensions`, `Resources`, `Attributes`, kept as separate collections.
- Declared fields expose a real `TypeDescription`: scalar types and their actual
  length/precision/date qualifiers, or a singleton reference to the same runtime's
  catalog type. See [reference descriptions](metadata-reference-types.md).
- Metadata objects expose `Name`, empty admitted `Synonym` / `Comment`,
  `FullName()`. Both method aliases return a Russian-family path.
- `FindByType(Type)` maps the admitted catalog/document families and register
  manager/selection/record families to their owner. A primitive type returns
  `Undefined`. A foreign runtime snapshot is explicitly rejected, even for the
  same database and metadata UUID.
- `FindByFullName(String)` traverses the bounded graph. Russian and English family
  segments are accepted, case-insensitively. A missing or unsupported path returns
  `Undefined` as an explicit local policy, not a measured native miss guarantee.

Example, with declared catalog `Products` and field `Text`:

```bsl
For Each Field In Metadata.Catalogs.Products.Attributes Do
    If Field.Type.ContainsType(Type("String")) Then
        Message(Field.Name + ": " + String(Field.Type.StringQualifiers.Length));
    EndIf;
EndDo;
Owner = Metadata.FindByType(Type("CatalogRef.Products"));
SameField = Metadata.FindByFullName("Catalog.Products.Attribute.Text");
```

Metadata-object collections support `Count`, `Find(String|Number)`, `Get(Number)`,
`IndexOf`, `Contains`, iteration, name properties and string/numeric indexing.
Membership is object identity, never host equality. Lookup misses return
`Undefined`; indexing misses raise an error. Method-name collisions require
string indexing or `Find`. Numeric indexes are zero-based. Top-level order comes
from current `Configuration.xml` ChildObjects, not SQL's alphabetical order.
Declared field/section order comes from the admitted schema. A custom logical
backend without source-order evidence still rejects multi-object numeric order.

## Standard descriptions are a different collection

`StandardAttributes` is `StandardAttributeDescriptions`, not a metadata-object
collection. It supports `Count()`, iteration and `[name|index]` only. Each item
has `Name`, `Type`, `Synonym`, `Comment`; no invented `FullName` or `Find/Get` API.

The bounded host exposes only standard fields implemented by its record adapters:

- Catalog: Ref, DeletionMark, Code, Description; Parent/IsFolder for the admitted
  hierarchical profile.
- Document: Ref, DeletionMark, Number, Date.
- Tabular section: LineNumber.
- Periodic information register: Period. Independent nonperiodic registers: none.

These are **not** a claim of the full native standard-attribute inventory or its
ordering. This local subset is enumerated in the order above; names are Russian
and lookup accepts both aliases. Recorder, Posting, DataVersion, Owner and other
unsupported fields are not fabricated. Standard attributes never enter custom
`Attributes` collections.

## Identity, immutability and boundaries

Each interpreter owns an immutable metadata snapshot. Lazy collections must
share the same database identity and configuration generation. Existing metadata
remains a description of that snapshot; record operations independently validate
current schema before use. Reference descriptions use the actual manager's bound
Type, never a reconstructed name or UUID. Later SQL-format migrations must use the
current admitted schema/source, not historical receipt snapshots.

All graph objects are read-only. Metadata and metadata-bound reference descriptions
are not admitted to generic serialization, ValueStorage, network/form transfer or
external Query tables. Scalar descriptions retain their existing supported codecs.
A missing database fails lazily with the catchable `db required` error. A configured
common-module registry and configuration name can be read without a database.
Nonempty presentation metadata is still rejected by the importer, not silently
replaced with Name. This block adds no SQL storage version or activation bypass.

`# !todo`: full metadata TypeOf/Type-name identities, additional metadata families,
localized presentation, native standard-attribute inventory/order, nested fullname
edge cases, and reference default/conversion/composite descriptions remain outside
this profile. Host-authored tests cover the bounded policy, not blanket 1C parity.

## Official contract and existing native evidence

The official EDT platform documentation defines MetadataObjectCollection's
Count/Find/Get/IndexOf/Contains, configuration FindByType/FindByFullName, field
TypeDescription properties, and the distinct StandardAttributeDescriptions API.
Source: [EDT documentation JAR](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar),
SHA-256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Within `nl/{ru,en}/html/SyntaxHelperContext/objects/catalog63/catalog272/`:
`ConfigurationMetadataObject/methods/FindByType1401.html`,
`ConfigurationMetadataObject/methods/FindByFullName2374.html`,
`catalog1728/MetadataObjectCollection.html`,
`catalog1728/catalog1736/StandardAttributeDescriptions.html`,
`catalog1506/object1556/properties/Type6908.html`.

Unchanged [native run 41193004501](https://github.com/Atridis/yadinassi/actions/runs/41193004501)
recorded 26 cases in six client/server × updated/loaded/applied captures.
`tests/fixtures/metadata_catalog_runtime/native_observations.json` stays byte-for-byte
unchanged. Replay now includes cases 07/08, previously excluded: declared Payload's
StringQualifiers.Length is 32 before applying the edited schema, 64 after applying.
Replay authors those logical schemas independently and compares the entire original
probe output; it does not create new native observations or validate the whole graph.

Application-local metadata/type scope and interruption/failure behavior are
specified in [application-family-lifecycle.md](application-family-lifecycle.md).
