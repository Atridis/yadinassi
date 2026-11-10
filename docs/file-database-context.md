# SQLite application database

Yadinassi uses its own SQLite file for imported configuration XML/BSL and
application data. It does not read native `.1CD`, CF/DT, CONFIG, PARAMS or
DBNames formats. The removed readers, physical fixtures and oracle routes remain
recoverable from Git history; they are not part of the supported installation.

## Import and open

Explicit CLI creation is separate from script execution:

```console
yadinassi --create-db application.sqlite --import-xml /path/to/designer-xml
```

The destination must not exist. `--inactive` stores an unsupported configuration
as an inactive source archive; it does not enable application-data execution.
Ordinary invocation and `--f` never create a missing database implicitly.

The Python import boundary accepts a mapping of relative Designer-export paths
to their exact UTF-8 bytes:

```python
from yadinassi.configuration_xml import import_configuration
from yadinassi.database_context import SQLiteDBContext
from yadinassi import Interpreter

configuration = import_configuration({
    "Configuration.xml": configuration_xml_bytes,
    "Catalogs/Products.xml": products_xml_bytes,
})
with SQLiteDBContext.create("application.sqlite", configuration) as context:
    runtime = Interpreter(database_context=context)
    try:
        runtime.execute("Сообщить(Метаданные.Справочники.Количество());")
    finally:
        runtime.close()
```

The mapping must be a complete admitted official XML subset, not arbitrary
XML matching these filenames. The importer checks identities, relative paths,
UTF-8, bounded XML structure, supported types and metadata semantics; DTD/entity
input is refused. Creation is exclusive: it never overwrites an existing file.
Accepted source files are stored with SHA-256 digests and can be exported by
`context.backend.export_configuration()` without reconstructing native binary
formats. Stored source does not imply executable support. Activation refuses
unsupported modules, metadata behavior and object families explicitly.
An optional [closed ConfigDumpInfo inventory](configuration-dump-info-profile.md)
can accompany the admitted catalog subset. It is checked against the parsed
object identities and retained unchanged, not treated as proof of full native
dump compatibility or executable semantics.

For an existing application database:

```console
yadinassi --f /path/to/application.sqlite program.bsl
```

`--f` selects an existing file, not a directory, and opts into the local
application/thick-client mode. Plain `yadinassi script.bsl` requires neither a
database nor a server, and never creates a database automatically. Separate
client-only/server-only modes are future work; their flags are not specified. Python callers use `SQLiteDBContext(path)`; the removed
`FileDBContext` is not a compatibility alias. Invalid storage fails explicitly.
The backend refuses remote/URI paths, symbolic-link aliases and invalid schema;
this is not authentication or a connection to a running 1C session.

## Behavior boundary

The current backend is a bounded catalog slice: schemas, standard fields,
primitive attributes and fixed catalog references, catalog objects and
transactional create/update. Admitted catalog tabular sections and [bounded relational queries](relational-catalog-queries.md)
are also supported. New document-bearing databases additionally support the
[bounded v7 non-posting document lifecycle](sqlite-document-lifecycle.md), with
separate document tables, metadata and identities. InformationRegisters, posting
and general configuration callbacks remain unsupported. Unsupported
semantics must not silently bypass validation or business logic. See the
[runtime catalog contract](bsl-catalog-read-scenario.md) and
[headless UI protocol](ui-protocol-v0.md) for their exact public surfaces.

`InfoBaseConnectionString()` / `СтрокаСоединенияИнформационнойБазы()` reports
`SQLite=<absolute selected file>`. This is deliberately the identity of the
application's host backend, **not** native `File=` connection-string parity.
Both aliases, arity and no-database errors retain their own tests. The native
1C observations remain unchanged; only the five explicitly identified
connection-shape slots in the ordinary host-preflight expectation differ.
No other native observations are masked or normalized.

## Native reference testing

Real 1C remains the behavioral reference through ordinary BSL and official
Designer XML load/dump operations. Its disposable native infobase may internally
use native storage, but that file is opaque to Python: no physical parser,
extraction or byte comparison is part of this workflow. Ordinary native
bootstrap, source provenance, process supervision and cleanup guards remain.

### Owned preflight fixture provenance

`scripts/native_infobase_fixture.py` contains the authored XML input mapping,
fixed synthetic metadata identities, generation SQLite version, exact SHA-256
and compressed source-encoded SQLite fixture. To regenerate, import that mapping
with `import_configuration`, create a new temporary SQLite file with
`SQLiteCatalogBackend.create`, and pin the generator's `uuid4()` to
`10000000-0000-4000-8000-000000000003` (the documented synthetic database ID).
Close the backend before reading the newly created file. Review its logical
schema/export against the input mapping, then update the encoded bytes, hash and
SQLite version together. Never substitute a native database or application data.
The regression test also creates a fresh database through the supported importer
and backend; its byte layout need not match across SQLite library versions.
