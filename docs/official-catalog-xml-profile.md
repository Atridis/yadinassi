# Closed Designer catalog XML profile

This is a deliberately narrow catalog admission increment, not support for
arbitrary 1C configurations. The existing source-owned
`scripts/catalog_object_behavior/generated/Catalog.xml` is the reference object.
Its complete semantic redump was independently verified in native acquisition
[41645005336](https://github.com/Atridis/yadinassi/actions/runs/41645005336).
The input originated as a transformed owned template; the evidence is Designer
load and verified redump, not a claim that it was created by the GUI.

The importer compares the whole catalog object against this one profile after
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

The surrounding minimal Configuration.xml used by the unit test is synthetic.
A real full Designer configuration also contains Language and many default
properties; this change alone does **not** activate such a complete export or
claim arbitrary Designer compatibility. `!todo`: acquire a safe owned full
Designer export and admit its known semantics without ignoring permissions,
modules, unknown metadata or automatic behavior. `!todo`: broader standard
presentation/attribute variants and real custom fields require separate bounded
validation and evidence. No 1CD/CF/DT parsing or migration of native 1C data is provided.

Unknown XML processing instructions are rejected in all imported XML files,
including auxiliary files; XML declarations remain allowed. Unsupported auxiliary
XML can be archived, but blocks activation. The optional
[closed ConfigDumpInfo inventory](configuration-dump-info-profile.md) is admitted
only after matching the known configuration, catalogs and custom attributes;
it never bypasses the semantic guards described here.
