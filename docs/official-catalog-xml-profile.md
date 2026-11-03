# Closed Designer catalog XML profile

This is a deliberately narrow catalog admission increment, not support for
arbitrary 1C configurations. The first source-owned
`scripts/catalog_object_behavior/generated/Catalog.xml` is the empty-field reference object.
Its complete semantic redump was independently verified in native acquisition
[41645005336](https://github.com/Atridis/yadinassi/actions/runs/41645005336).
The input originated as a transformed owned template; the evidence is Designer
load and verified redump, not a claim that it was created by the GUI.

The importer compares the whole catalog object against a closed profile after
expanding element/attribute namespaces and QName-valued `xsi:type`. It normalizes
only the catalog name, its UUID, the ten validated generated type/value UUIDs,
and supported Code/Description lengths. All generated names must use the actual
catalog name, all eleven identities must be distinct, and generated identities
must not collide with other configuration metadata identities. Unknown nodes,
attributes, altered StandardAttributes, behavior flags, child objects, values,
namespace rebinding and other changes never disappear from the comparison. The
SHA-256 fingerprint is a compact representation of that full normalized structural
comparison, not a broad list of fields to ignore. Nonmatching catalogs follow the
existing restrictive import/activation path.

This fixture has no custom attributes, hierarchy, owners, child objects, modules,
predefined data, data history, automatic numbering, or non-default fill checking.
Explicit Code strings and Description are written through the normal SQLite
backend. Exact source files remain stored/exported unchanged. Existing limits on
metadata size, source files and the record/backend model remain in force.

## Owned scalar-attribute profile

A separate whole-catalog fingerprint admits
`scripts/catalog_query_behavior/generated/Catalog.xml`. Its strict complete
semantic Designer redump was verified in native acquisition
[41511900693](https://github.com/Atridis/yadinassi/actions/runs/41511900693).
That run also recorded runtime comparison differences. This XML admission does
**not** establish corrected-source runtime parity; see
[the query evidence boundary](catalog-query-v1.md#evidence-boundary).
Neither the fixture, its prospective source manifest, nor measured native outputs
are changed by this importer increment.

This profile requires exactly three ordered direct attributes: Number(12,2,Any),
Boolean and DateTime(DateTime). The catalog/field names and metadata UUIDs may
change. Names must remain valid identifiers, field names cannot collide with
reserved standard/runtime members or each other (case-insensitively), generated
type names must use the actual catalog name, and all fourteen identities must be
distinct. Generated and field identities are also checked against every other
configuration/catalog/field identity. Existing Code 1–64 and Description 0–1024
length bounds remain available. Different scalar qualifiers, field types,
references, counts or ordering require a new separately reviewed profile.

Both `v8:Type` values and `xsi:type` attributes are compared using their actual
in-scope namespaces, so legal aliases are accepted but namespace rebinding cannot
change a type or default unnoticed. Every other element, attribute, scalar value
and meaningful text remains in the fingerprint, including all catalog standard
attributes and all custom-field properties. The defaults are exactly decimal
`0`, Boolean `false`, and `0001-01-01T00:00:00`; FillFromFillingValue remains false,
FillChecking DontCheck, bounds nil, Use ForItem, Indexing DontIndex, and history
and search disabled. Nothing is inferred from a partial property match.
Unrecognized, missing or altered properties take the restrictive path and cannot
activate. Executable modules remain independent activation blockers.

The existing typed catalog runtime and per-catalog/per-field SQLite layout are
unchanged. Local coverage creates default and explicitly populated records,
closes/reopens SQLite, reads and queries all three fields, checks their type
qualifiers and verifies that original XML exports byte-for-byte unchanged.
Negative mutations cover defaults, namespaces, inventory, unknown/executable
components, UUID/name collisions and type/reference substitutions.

The surrounding minimal Configuration.xml used by the unit test is synthetic.
A real full Designer configuration also contains Language and many default
properties; this change alone does **not** activate such a complete export or
claim arbitrary Designer compatibility. `!todo`: acquire a safe owned full
Designer export and admit its known semantics without ignoring permissions,
modules, unknown metadata or automatic behavior. `!todo`: broader standard
presentation/attribute variants and other custom fields require separate bounded
validation and evidence. No 1CD/CF/DT parsing or migration of native 1C data is provided.

Unknown XML processing instructions are rejected in all imported XML files,
including auxiliary files; XML declarations remain allowed. Unsupported auxiliary
XML can be archived, but blocks activation. The optional
[closed ConfigDumpInfo inventory](configuration-dump-info-profile.md) is admitted
only after matching the known configuration, catalogs and custom attributes;
it never bypasses the semantic guards described here.
