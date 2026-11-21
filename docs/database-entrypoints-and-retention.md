# Database entrypoints and retention audit

This map describes the code at the bounded-read audit checkpoint. It is not a
new profile grant, migration mechanism, or statement of native 1C parity.

## Entrypoints and explicit grants (A3)

| Entry | Admission | What it does not grant |
| --- | --- | --- |
| `SQLiteDBContext(path)` / `SQLiteCatalogBackend(path)` | Existing exact SQLite format/schema and source checks | Opening does not execute configuration modules |
| `SQLiteDBContext.create` | Imported configuration, activation flag (defaults to True) | Unsupported metadata is not activated by copying XML |
| `create_posting`, `create_accumulation` | Exact canonical posting/accumulation configuration | Existing ordinary DB is not upgraded; table presence is not a grant |
| `create_inventory`, `create_inventory_enum` | Separate typed-reference / enum profiles | Core data capability is not a full application/form grant |
| `create_inventory_application`, `create_inventory_enum_application`, `create_main_demo` | Exact full-source profile type, source digest, canonical schema | No arbitrary source, generic migration, or Enterprise compatibility |
| `SourceConstantStore.create/reopen/load_source/update_source` | Separate scratch DB schema, file identity, source/codec binding | Not the numbered ordinary SQLite backend formats; source load does not run startup |
| `SQLiteCatalogBackend.launch_snapshot` | One admitted read snapshot, canonical source and schemas | Returns detached launch input, not activation, writable data or running VM |
| `begin_unit_of_work` | Formats 11–16, ordinary write admission | Does not give BSL ownership, form dispatch or arbitrary callback authority |
| `database_transactions.begin/commit/rollback` | Admission token and current synchronous execution owner | No detached/foreign owner or automatic source-profile widening |
| `database_transactions.require_host_root` | Exact v13 PostingApplicationConfiguration, canonical source, no BSL execution owner | Not the generic root for accumulation or arbitrary source applications; specialized roots retain their own admission |
| `database_transactions.query_view` | Ordinary admitted read outside a transaction; registered exact query lease inside | Not duck-typed access to any object exposing a connection |

The launch adapter is narrower than storage support. `sqlite_launch._admit`
selects full-source application routes for v13/v15/v16, explicit legacy routes
for v6/v7, and tightly restricted plain catalog routes for v1/v2/v3/v4/v10/v11/v12.
It refuses other profiles rather than inferring activation from available tables.
In particular, `launch_snapshot` does not advertise every storage format as UI-ready.

Keep historical fixtures and their identity/hash boundaries. Consolidating the
user-facing demo does not authorize rewriting captured native evidence or
silently converting old DB formats. There is no new migration engine in this audit.

Implementation anchors: `database_context.py`, `sqlite_catalog.py`,
`sqlite_launch.py`, `source_constant_store.py`, `database_transactions.py`,
`inventory_enum_runtime.py`, and the explicit `sqlite_*_profile.py` modules.

## Write outcomes and maintenance

A write returns typed outcomes only after confirmed COMMIT. There is no durable
business receipt, acknowledgement protocol, or replay. After an unknown
outcome, close resources and read the current database state independently.
See [unknown commit outcomes](sqlite-commit-uncertainty.md).

An existing database is never changed on open. The storage migration tool is
a separate, explicit maintenance operation; changes to supported layouts do
not authorize running it on user data.
