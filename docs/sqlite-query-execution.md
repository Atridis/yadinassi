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

## Fields of a reference in a query

A flat SQLite query can project fields through a declared reference. For
example, fetch a document's caption and code for the same warehouse in the
query itself:

```sql
SELECT D.Warehouse.Description AS Caption, D.Warehouse.Code AS WarehouseCode
FROM Document.Receipt AS D
WHERE D.Ref = &Receipt
```

SQLite runs one data statement. The two fields share one `LEFT JOIN`; a
reference to the current header, such as `D.Ref.Number`, needs no additional
join. An empty reference produces query `NULL` in the projected fields.
The same typed path is available for physical catalog and document headers
and their tabular sections, independent information registers, and raw
recorder and accumulation rows. The reference must have one declared target
supported by the opened SQLite layout.

This is a one-hop, field-only projection with ordinary source comparisons,
ordering and `TOP`. Polymorphic reference paths, virtual tables, hierarchical
layouts, computed expressions and aggregate or nested dereference queries
are not covered by this path. The ordinary script expression
`S.Ref.Description` retains its live read behavior; only an explicit query
projection captures the value as part of the query result.
