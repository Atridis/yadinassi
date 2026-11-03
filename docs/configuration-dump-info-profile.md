# Closed ConfigDumpInfo XML inventory

`ConfigDumpInfo.xml` is optional bookkeeping beside `Configuration.xml`, not
an executable configuration or proof that imported files are complete or current.
The importer now admits a small, explicitly checked inventory for its existing
catalog XML subset. Original UTF-8 bytes, including a BOM, XML declaration and
line endings, remain unchanged in `ConfigurationImport.files`. It does not
generate, repair or update version files.

## Sources and evidence

The [1C Administrator Guide 8.3.27, section 3.18](https://1c-dn.com/library/tutorials/1c_enterprise_administrator_guide_file_mode_8_3_27/?sphrase_id=1888935)
documents a UTF-8 `ConfigDumpInfo` root, one `ConfigVersions` container, object
`Metadata` records and nested records for subordinate objects such as attributes.
It defines `format`, `version`, `name`, `id` and `configVersion`, describing
the last two as internal platform values.

The [1C Developer Guide 8.3.27, section 2.17.4](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293)
explains that object version strings support incremental export. They are not
metadata semantics or hashes this importer can recompute.

A [public source example](https://github.com/alexandrkakushin/1c_building/blob/master/ConfigDumpInfo.xml)
illustrates the dumpinfo namespace, qualified names, UUID object identities,
40-hex version strings and nested attribute identities. It uses format version
2.7 and includes many objects outside this implementation. It is **not** our
native measurement, a fixture imported into this repository or evidence that
its configuration can run here. The new inventory fixtures are synthetic.

## Admitted subset

- Exact root-level filename `ConfigDumpInfo.xml`.
- Namespace `http://v8.1c.ru/8.3/xcf/dumpinfo` for every element; namespace
  prefix spelling and unused namespace declarations do not affect meaning.
- Root attributes exactly `format="Hierarchical"` and `version="2.20"`.
  This is the existing MVP's supported format, not a claim about every Designer
  release. `Configuration.xml` and every imported catalog document must also
  declare `2.20`. Mixed or other versions remain outside this profile.
- Exactly one attribute-free `ConfigVersions` child. Its direct children must
  be `Metadata` records with exactly `name`, `id` and `configVersion`.
- Exactly one `Configuration.<name>` record and one `Catalog.<name>` record
  for each catalog in the imported configuration. Names are exact and
  case-sensitive. UUIDs must match the parsed objects; canonical hyphenated
  nonzero UUIDs are required, with either hexadecimal letter case allowed.
- Each custom catalog attribute appears exactly once as a direct child of its
  own catalog record, named `Catalog.<name>.Attribute.<attribute>`, with its
  actual UUID. Attribute records are leaf nodes with only `name` and `id`.
  Configuration records have no nested records in this subset.
- `configVersion` is restricted to the observed 40-hex lexical form. Values
  are opaque, may repeat and are not verified against content. This deliberate
  narrow admission limit is not a universal 1C format specification.
- Record order, comments and XML formatting whitespace are inert, subject to the global DTD/entity prefilter (which also rejects those literal tokens in comments). Other text,
  unknown elements/attributes, duplicate or missing records, foreign namespaces,
  unmatched identities and unsupported shapes block activation. A declaration,
  when present, must specify XML 1.0 and UTF-8 or omit the encoding.

The existing byte, file-count, depth and element-count limits still apply.
Invalid XML, non-UTF-8 input, DTD/entity declarations and processing instructions
are rejected before import. Other out-of-profile XML remains a preserved source
archive with an activation issue, as before.

## Deliberate limits

Module/component records, dotted identity suffixes, languages, forms, templates,
predefined items, tabular sections and other object families are unsupported.
An accepted inventory never removes issues found in actual XML or BSL files.
Comment-only BSL files retain their existing archival treatment; executable
module code remains blocked, even when the known XML inventory matches.

The inventory is only checked against known catalog objects and attributes.
It does not certify an entire native dump, grant permissions, enable business
logic, establish version freshness or replace the independent semantic guards.
A full Designer `Configuration.xml` still has unadmitted properties and object
families. This increment neither provides full Designer-export support nor
changes SQLite, UI, native bootstrap or native data handling. Future broader
admission needs separate bounded semantics and suitable owned native evidence.
