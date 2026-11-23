# SQLite Query execution

A Query over an already open SQLite database binds against the metadata
admitted when the backend opened. It can borrow a read-only connection
without rereading the database generation, XML, or stored schema
definitions. An eligible COUNT(*) issues one SQL statement,
without inspecting fields that do not contribute to its result.

If the executing BSL code already owns a transaction, the query borrows its
connection and sees the transaction's writes. It does not commit or roll back
the caller's transaction. Otherwise, a single SQL statement uses normal
SQLite read consistency. Composed queries with multiple stored source reads
share one read snapshot; internally paginated reads of a single source do
not imply a snapshot across pages. Use an explicit transaction when several
separate queries must agree. These rules do not change temporary-table
publication, typed reference ownership, or the admission and validation used
by object access and writes.

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

This is a one-hop, field-only projection with typed source comparisons
combined by `AND` or `OR`, ordering, `TOP` and `DISTINCT`. With `DISTINCT`,
order expressions must be projected. `TOP 1` can use the physical first row
because equivalent duplicates have equal sort keys. Other distinct queries
read one sorted, bounded input, validate its source and reference witnesses,
then deduplicate with the normal typed query keys before applying `TOP`.
They preserve the first spelling of case-insensitively equal strings and keep
`NULL` distinct from an empty string. Polymorphic reference paths, virtual
tables, hierarchical layouts, computed expressions and aggregate or nested dereference queries
are not covered by this path. The ordinary script expression
`S.Ref.Description` retains its live read behavior; only an explicit query
projection captures the value as part of the query result.

### Reading query rows without one SQL request per row

For report fields that should reflect the query result, read the selected
column, not the live reference. If the field already belongs to the selected
row, it does not need a join:

```bsl
Q = New Query("SELECT TOP 512 Ref, Description FROM Catalog.Склады ORDER BY Code");
S = Q.Execute().Select();
While S.Next() Do
    Message(S.Description);
EndDo;
```

Use an explicit dotted query projection and its alias for a field of another
object, as in the warehouse example above. The same rule applies to
references from supported tabular sections and register rows: project the
fields needed by the report, and keep the reference itself only if the script
also needs it.

Do not substitute a projected column for a deliberately live read. A write
from another connection after `Execute()` can change
`S.Ref.Description` without changing `S.Description` in the held selection.
Empty references can differ too: a dotted query path can yield `NULL`, while
a live reference property can have a typed default. The translator therefore
does not rewrite one form into the other.
