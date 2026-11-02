# SQLite catalog application baseline

Configuration import accepts bounded UTF-8 official Designer XML-shaped metadata
and BSL files, retaining their exact bytes inside SQLite. The admitted active
schema is flat catalogs with explicit unique String codes, descriptions, scalar
String/Number/Boolean/DateTime fields and single typed catalog references.
Unknown behavior and executable modules produce activation issues; hooks are
never silently skipped. This is a storage/catalog baseline, **not yet the full
configured-application MVP**. Supported form/object-module activation is the
next integration step, rather than a permanent comment-only-code restriction.

The BSL path supports `Catalogs.Name`, `EmptyRef`, `GetRef`, exact `FindByCode`,
explicit-exact `FindByDescription`, `Select` / `Next`, reference fields/Metadata /
UUID / GetObject, `CreateItem`, detached CatalogObject field edits, `IsNew`,
`SetNewObjectRef`, and `Write`. CatalogObject dynamic type identity and codec
refusal are explicit. Selection order is the backend's `code_then_identity`
contract, not a claim of native collation parity. Selection restart and retained
last-row behavior are covered by logical regression tests.

Editing or discarding an object does not persist it. Successful Write atomically
creates/updates one record; optimistic revisions reject stale edits. Validation
and duplicate-code failures retain the edit buffer. An uncertain commit keeps
its exact operation identity and submitted intent; retry resolves the durable
receipt before another write, and edits are blocked until resolved. References
are checked against the owning database, target catalog and interpreter schema.

Inactive imported configurations can be archived/exported separately from
activation; they must not expose catalog operations or execute unsupported
configuration code. SQLite owns transactions and indexes; no native-file writer,
CF/DT lifecycle or physical-layout compatibility exists.

`!todo`: generic module/form execution, automatic code allocation, hierarchy,
composite fields, deletion, query language, and SQLite Documents/Registers are
outside this baseline. Existing unrelated language/collection behavior remains
independently supported.
