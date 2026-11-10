# Independent information-register queries

The owned SQLite v8 profile supports `InformationRegister.Name` /
`РегистрСведений.Name` as a read-only Query source for independent, nonperiodic
registers. This is a bounded host contract, not measured native 1C query parity.

All declared dimensions, resources, and attributes are available with their
exact scalar types and qualifiers. Catalog-reference fields keep their target
catalog and interpreter metadata snapshot. Rows have a complete dimension key;
there is no implicit Ref, Period, Recorder, LineNumber, or owner field. A field
exists only when it is declared in the admitted register metadata.

```bsl
Q = New Query("SELECT Key, Amount FROM InformationRegister.Rates WHERE Enabled=TRUE AND Amount>=&Minimum ORDER BY Key");
Q.SetParameter("Minimum", 10);
Table = Q.Execute().Unload();
```

`Key`, `Amount`, and `Enabled` above are example metadata fields. They are not
standard register fields. See [the report example](../examples/information-register-report.bsl)
for a two-stage report joining reference dimensions to a catalog.

## Composition and identity

Sources compose with catalog and document sources, joins, WHERE, computed
expressions, GROUP BY/HAVING, aggregates, TOP, DISTINCT, UNION, typed external
ValueTable sources, and temporary-table packages. A mixed query or package
uses one logical application read transaction. Metadata needed by later
statements is initialized before that transaction, including catalog-first
packages. Register-only databases do not require document metadata.

Scalar Unload preserves the declared schema even for an empty result. Dynamic
reference columns remain cursor-only; their Unload, TypeDescription transport,
and internal-value codecs are not expanded. Register managers and records do
not become accepted query parameters or fabricated reference values.

Stored String dimension keys are exact and may differ only by case. Query
String comparison, grouping, and DISTINCT retain the existing casefold policy;
this does not merge or delete the underlying register records.

## Bounds and failure behavior

Queries consume explicit logical continuation pages, not the ordinary bounded
manager Select result. More than 1,000 records are supported, up to the existing
10,000-input-row bound. Every dimension, resource, and attribute is validated,
even when not projected. Full records count toward the shared 100,000-cell and
8,000,000-character input budgets. Overflow fails rather than returning partial
aggregates, including when TOP would show only a few rows.

Malformed records, wrong schema/database/revision identity, duplicate dimension
keys, or repeated continuation tokens fail closed. Read views close on success
and error; failed packages publish no temporary-table changes. Query does not
write register rows, change schema, or upgrade an older SQLite database.

Periodic/recorder-dependent registers, slice virtual tables, arbitrary SQL,
record references, and data modification through Query text remain unsupported.
