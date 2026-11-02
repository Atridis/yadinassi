# Bounded ordinary XDTO family

This checkpoint adds an end-to-end typed-data workflow: read explicit owned XSD
files with `CreateXDTOFactory`, create typed scalar/object/list values, inspect
readonly type/property/package metadata, and read/write XML or JSON through the
existing readers/writers. **Initial ordinary40 real 1C acquisition is available**; all40 actions succeeded
on managed client and server. The retained capture calibrated two differences:
attribute-first property metadata and false IsSet for an empty repeated field.
Fresh exact-head native acceptance is pending; local replay is not a new native run. The fixed ordinary40 acquisition is described in
[xdto-family-measurement.md](xdto-family-measurement.md).

## Public ordinary surface

* `XDTOFactory`: empty constructor, `Type`, `Create`, `Packages`, `ReadXML`,
  `WriteXML`, `ReadJSON`, `WriteJSON`; per-interpreter global factory and
  `CreateXDTOFactory(filename | ArrayOfFilenames)`.
* `XDTODataObject`: named properties/index access, `Get`, `Set`, `GetXDTO`,
  `GetList`, `IsSet`, `Unset`, `Type`, `Factory`, `Owner`, `OwningProperty`,
  `Properties`, `Validate`.
* `XDTODataValue`: readonly `Value`/`LexicalValue`, `Type`/`Factory`.
* `XDTOList`: Count/Get/GetXDTO/Add/Insert/Set/Delete/Clear, index and iteration.
* Readonly object/value types, properties and their collection, packages and
  their collection; ordinary identity/name/namespace/bounds/form metadata.
* Builtin `string`, `boolean`, `decimal`, `integer`, `int`, `long`, `date`,
  `dateTime`, `base64Binary`. Numeric conversion admits bounded exact numbers
  and lexical strings, not arbitrary host coercion.

## Closed schema subset

Explicit local file paths only; at most eight files and 256 KiB combined. A
schema has a nonempty target namespace, named acyclic complex types, one ordered
sequence of explicitly typed elements, scalar attributes and explicit global
root elements. Optional/repeated/nillable fields and qualified/unqualified
forms are admitted. Parsing never resolves imports, URLs or external entities.
Unsupported constructs/attributes are rejected, not ignored or flattened.

!todo No import/include/redefine, recursive/mixed/choice/any content,
inheritance, restrictions/facets/custom simple types, anonymous types, defaults,
fixed values or full XMLSchema object/compiler API. No implicit database or
configuration schema loading. `IsDescendant` currently only recognizes exact
identity; builtin inheritance is not represented.

## Integrity and resource boundaries

The factory tracks at most 10,000 allocated graph nodes/list entries and 4 Mi
lexical Unicode code points over its lifetime; failed typed reads restore the
allocation ledger and borrowed reader cursor. Values have 256 Ki code-point
limits; numerical coefficient/exponent and binary input sizes are checked
before expansion. CPython Decimal allocation size is an admission check, not a
portable semantic guarantee. At most 128 schema object types, 256 properties,
32 levels, 4096 entries per list; schema XML also has a 2048-node bound. Before XML/JSON tokenization the input is capped at 256 KiB/code points;
tokenization uses the existing bounded parser limits (not the tighter XDTO
model limits). The XDTO node/depth/property limits are enforced before building
the typed model. Existing XML/JSON parser/writer limits remain unchanged. Unknown/duplicate JSON fields,
unknown XML fields, invalid order, foreign owners/types and cycles fail before
publishing a graph or replacing a property. Unsupported codec roundtrips fail
explicitly; these objects are not portable process-serialization values.

File access reuses existing explicit regular-file capability and stream path
checks; this is not a new filesystem sandbox. Schema text is untrusted even
when its pathname is supplied explicitly. All native fixture paths are freshly
owned temporary paths and are removed by exact-name cleanup.

## Explicit provisional / unsupported behavior

The retained ordinary40 fixture covers observed list returns, unset/list identity,
scalar lexical spellings, metadata flags and XML/JSON roundtrips. !todo Unmeasured
multiple-attribute relative ordering and alternate lexical/serialization modes
are not generalized from that finite capture.
Only direct property names are supported, not XPath expressions. XML/JSON reads
start at the beginning of a borrowed reader; callbacks, alternate type-assignment
modes and positional reads are rejected. XML writes support element form;
qualified attribute writing is rejected rather than silently losing its URI.
No arbitrary host objects, network access, external entity/DTD resolution or
security/cryptographic claims are introduced.
