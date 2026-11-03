# Closed configuration module inventory

Importing a source file does not authorize executing it or inventing a metadata
owner. The catalog XML importer recognizes only these canonical hierarchical
module paths:

- `Ext/ManagedApplicationModule.bsl`
- `Ext/OrdinaryApplicationModule.bsl`
- `Ext/ExternalConnectionModule.bsl`
- `Ext/SessionModule.bsl`
- `Catalogs/<declared catalog name>/Ext/ObjectModule.bsl`
- `Catalogs/<declared catalog name>/Ext/ManagerModule.bsl`

The root paths bind to the configuration metadata UUID. Catalog paths bind to
the UUID of the catalog whose name exactly matches its XML filename and declared
name. This is a deliberately closed importer policy: directory, filename,
extension and catalog-name spelling must match exactly. It is not a claim about
native operating-system case handling. Case-colliding source paths retain the
existing global rejection.

The [1C Developer Guide 8.3.27, section 2.17.3.1](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1678862)
documents the four configuration module filenames and the hierarchical object
`Ext` layout. Its section 2.17.5.3.6 gives the catalog `ObjectModule.bsl` path.
The official [module types tutorial](https://1c-dn.com/library/tutorials/practical_developer_guide_theory_module_types/)
describes the object and manager modules available for catalogs. The other module
kinds listed for other configuration object families do not authorize adding
them under a catalog or the root. Common modules, command/form modules, other
object families and unlisted module names remain outside this importer profile.

Empty, whitespace-only and comment-only source at a recognized path keeps the
existing safe activation behavior. Any source with code still adds an independent
`module execution unsupported:<path>` activation issue. Import never executes
BSL, starts a session, resolves module imports or changes native configuration.

An unknown, misplaced or wrong-owner BSL path adds
`unsupported module path:<path>` even when it contains no executable code.
Exact per-path diagnostics are retained only while both bounds hold: at most
32 unknown paths and at most 8,192 characters in their compact, ASCII-escaped JSON
array, including quotes, commas and brackets. The length calculation uses
`ensure_ascii=True`, including paired surrogate escapes for astral Unicode.
Exceeding either bound produces one explicit `unsupported module paths:<count>`
summary stating that the individual paths remain in the configuration files. This bound
applies only to unknown-module-path diagnostic presentation: every source file is
still checked, all source paths and bytes are retained, and activation stays
blocked. Independent executable-code and XML issues are not removed or summarized.
Its exact source bytes remain in `ConfigurationImport.files` and in an inactive
SQLite archive, but it is not given a fabricated owner in
`ConfigurationImport.modules`. A known executable module retains its accurate
owner binding while blocking activation. Unknown executable source has both
issues. A valid path never clears issues from the other XML or BSL files.

The existing source limits, XML semantics checks and all-or-nothing activation
remain unchanged. Inactive archive creation is still subject to the global
source, schema and SQLite diagnostic budgets; this change does not raise those
limits or guarantee archival of every unsupported configuration. It prevents a
large otherwise-admissible unknown-module inventory alone from exhausting the
SQLite diagnostic budget. Tests cover the six known module kinds, exact metadata-owner
binding, unsupported names/families/locations, casing aliases, executable source,
byte-preserving inactive archive/reopen and safe empty-module activation/reopen.
The large-inventory regression uses 300 distinct 248-character paths whose
unbounded diagnostic list occupied 82,501 serialized characters, and checks the
summary, blocked activation and exact source archive after reopening SQLite.
The Unicode regression uses 32 distinct 248-character paths with astral characters,
whose unbounded diagnostic list occupied 93,281 serialized characters. Boundary
cases cover both 32/33 paths and JSON lengths 8,191/8,192/8,193. Independent code
and XML diagnostics remain visible under either summary trigger.
This is a local importer integrity rule, not native module-execution parity or
support for a complete Designer export.
