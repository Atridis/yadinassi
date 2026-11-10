# Document queries over owned SQLite databases

`Query` / `Запрос` can read document headers and tabular sections from the
already activated SQLite document profile. This is a bounded, read-only host
contract, not a claim of native 1C query compatibility. It adds no posting,
register movements, native document presentation, or reference serialization.
The database must already contain supported document metadata and records.
Queries neither activate unknown metadata nor modify stored configuration XML.

## Sources and fields

Use `Document.Orders` or `Документ.Orders` for headers and
`Document.Orders.Lines` or `Документ.Orders.Lines` for a tabular section.
Names refer to imported metadata, not physical SQLite tables. Document and
catalog namespaces remain separate: `Catalog.Orders` cannot substitute for
`Document.Orders`.

Header fields:

- `Ref` / `Ссылка`: the document reference in this interpreter's metadata snapshot.
- `Number` / `Номер`: the configured string number.
- `Date` / `Дата`: the document date and time.
- `DeletionMark` / `ПометкаУдаления`: Boolean deletion mark.
- `Posted` / `Проведен` / `Проведён`: always false in the non-posting profile.
- Supported custom fields declared in the document metadata.

Section fields are `Ref` / `Ссылка` (the owner document), `LineNumber` /
`НомерСтроки` (one-based), and the section's own custom fields. A section does
not inherit its owner's Number, Date, Posted, DeletionMark, or custom fields.
Join the owner explicitly when these are needed.

```bsl
Q = New Query("SELECT D.Number, L.LineNumber, L.Amount FROM Document.Orders.Lines AS L JOIN Document.Orders AS D ON L.Ref=D.Ref ORDER BY D.Number, L.LineNumber");
S = Q.Execute().Select();
While S.Next() Do
    Message(S.Number);
    Message(S.LineNumber);
    Message(S.Amount);
EndDo;
```

`Amount` and `Lines.Amount` in these examples are custom metadata fields, not
built-in document fields.

## Reports, parameters, and packages

The existing relational query profile applies: projection, exact typed
parameters, WHERE, JOIN, GROUP BY, HAVING, computed numeric expressions,
aggregates, ORDER BY, TOP, UNION / UNION ALL, and temporary-table packages.
Catalog-reference custom fields can join matching catalog references.
Section `Ref` can join its document owner. Document references retain their
kind, target metadata identity, and interpreter snapshot through temporary
tables and compatible UNION branches. A catalog reference, a reference to
another document type, or a reference from another interpreter is not an
interchangeable key. Invalid reference comparisons fail even on empty inputs.

```bsl
Q = New Query("SELECT Number, Amount FROM Document.Orders WHERE Date>=&Since AND Posted=FALSE ORDER BY Number");
Q.SetParameter("Since", Date(2026, 11, 1));
Table = Q.Execute().Unload();
```

See [the complete report example](../examples/document-query-report.bsl).
It first groups section amounts by owner into a temporary table, then joins
headers and customer catalog records. Aggregating lines first prevents header
amounts from being counted once per line. Its inner joins intentionally omit
orders without lines or a matching category. The script reads existing data;
it does not create or post documents.

## Results and boundaries

Scalar `Unload()` results preserve supported types and qualifiers, including
empty results. Unaliased `Number`, `Date`, and `Posted` keep their parser field
names. Use explicit aliases when stable column names are needed; use
`DeletionMark AS Deleted` when unloading that field, because the existing
unaliased DeletionMark unload restriction remains in effect.

Reference columns are available through a selection cursor. `Unload()` for
dynamic-reference columns remains unsupported, including for empty results.
This feature does not add dynamic-reference `TypeDescription` support or
internal-value codec representations. Do not turn references into guessed
strings for transport between interpreters.

A mixed catalog/document query or package uses one composite read view, even
when its first statement reads a catalog. Completed results are detached, and
the read view is closed on success or failure. Package failure rolls back its
temporary-table changes. Document scans use bounded continuation pages rather
than silently stopping after the first 1,000 records. Existing query resource
limits still apply; this is not unbounded SQL execution. The evaluator reads one
logical document card per page, checks every header and section value (including
unprojected fields), and counts them against the shared 100,000-cell and
8,000,000-character input budgets. At most 10,000 documents or selected section
rows are admitted per source; overflow fails even when TOP would return fewer
rows. A stored document retains its existing 1,000-total-section-row bound.
No query result is returned until the full input has been validated.
Ordinary Documents.Name.Select keeps its separate 1,000-match fail-on-overflow
contract. No schema migration, persistent index, or configuration rewrite is needed.

The same queries work with a read-only database. They do not change persisted
records or configuration files. Posting, document writes through query text,
and arbitrary SQL remain outside this query profile.

## Validation scope

`tests/test_document_queries.py` uses an authored XML-shaped configuration and
real owned SQLite storage. It covers English/Russian sources, report execution,
scalar metadata, joins and sections, identity rejection, temporary tables,
UNION, read-view cleanup, and unchanged read-only database/configuration bytes.
These tests and the example are host-contract checks, not a native 1C manual
run or a replacement for one where native parity evidence is required.
