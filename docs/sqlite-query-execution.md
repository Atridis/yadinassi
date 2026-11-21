# SQLite Query execution

A Query over an already open SQLite database binds against the metadata
admitted when the backend opened. It borrows a read-only connection, without
starting a snapshot transaction or rereading the database generation, XML,
or stored schema definitions. An eligible COUNT(*) issues one SQL statement,
without inspecting fields that do not contribute to its result.

If the executing BSL code already owns a transaction, the query borrows its
connection and sees the transaction's writes. It does not commit or roll back
the caller's transaction. Otherwise, SQLite provides its normal per-statement
read consistency. A query that still uses several SQL statements internally
does not promise one snapshot across those statements; consistent reads
across statements can use an explicit transaction. Query changes do not alter
temporary-table publication, typed reference ownership, or the admission
and validation used by object access and writes.

Apply configuration changes through the database lifecycle and reopen the
backend to bind new metadata. External SQL that edits the configuration or
schema in place is not a way to refresh a running query's metadata.
