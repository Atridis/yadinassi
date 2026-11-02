# Logical catalog metadata

`Metadata` / `Метаданные` and `.Catalogs` / `.Справочники` load lazily from the
SQLite application's normalized configuration schema. `SQLiteDBContext` is the
supported database context. Native binary database/configuration formats are not
supported.

Supported: `Count`, `Find(String|Number)`, named property/string-index lookup,
`Name`, `FullName`, and numeric index zero for a single-catalog schema. Metadata
is read-only. Names are case-insensitive; absent `Find` returns Undefined.
Method-name collisions require string indexing or Find. Multi-catalog numeric
ordering, attribute reflection and metadata iteration remain unsupported.

One interpreter caches schema identity and generation. Catalog row operations
verify that generation before using it; metadata identities are not physical
file addresses. A missing context raises the catchable `db required` error only
when database access is executed. Untaken branches and ordinary non-database BSL
remain usable.

Documents and information registers have no SQLite implementation yet and fail
explicitly. Neutral value/type identity classes do not imply database support.
