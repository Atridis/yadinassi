# Relational reports over catalog objects

`Query` / `Запрос` now combines saved catalog objects and their tabular sections
into one read-only report. This is a substantial local functional extension of
the [existing catalog query API](catalog-query-v1.md), not a new storage format
or a claim of complete native 1C query parity.

```bsl
Q = New Query;
Q.Text = "SELECT P.Code AS Product, C.Description AS Category, SUM(L.Amount) AS Total, COUNT(*) AS Lines
|FROM Catalog.Products AS P
|INNER JOIN Catalog.Products.Lines AS L ON P.Ref = L.Ref
|LEFT JOIN Catalog.Categories AS C ON L.Category = C.Ref
|WHERE L.Amount >= &Minimum
|GROUP BY P.Code, C.Description
|HAVING SUM(L.Amount) > 0
|ORDER BY Total DESC, P.Code";
Q.SetParameter("Minimum", 0);
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Product);
    Message(Rows.Total);
EndDo;
```

Run with `--f EXISTING.sqlite` using an admitted configuration whose Products
catalog has the shown Lines section, Amount Number and Category reference fields.
No database is implicitly created or activated. An unsaved object's buffer is
not a query source. Results are detached, and reopening a saved database retains
the same report inputs.

## Admitted language

- `INNER JOIN` / `ВНУТРЕННЕЕ СОЕДИНЕНИЕ`, `LEFT [OUTER] JOIN` /
  `ЛЕВОЕ [ВНЕШНЕЕ] СОЕДИНЕНИЕ`, and bare `JOIN`, followed by `ON` / `ПО`.
  Each source is `Catalog.Name` / `Справочник.Имя`, optionally with a tabular
  section and `AS` / `КАК` alias. Self-joins and chains of joins are supported.
- ON and WHERE admit exact-type field-to-field comparisons as well as existing
  parameters/literals, parentheses, AND and OR. A source's ON condition cannot
  refer to a later source. Ambiguous unqualified fields are rejected.
- `GROUP BY` / `СГРУППИРОВАТЬ ПО`, `HAVING` / `ИМЕЮЩИЕ`, and
  `COUNT` / `КОЛИЧЕСТВО`, `SUM` / `СУММА`, `AVG` / `СРЕДНЕЕ`,
  `MIN` / `МИНИМУМ`, `MAX` / `МАКСИМУМ`.
- `COUNT(*)` counts rows, including an unmatched LEFT JOIN row. `COUNT(field)`
  counts non-Null values. Other aggregates ignore Null and return Null for an
  empty input. With no GROUP BY, an empty aggregate input still returns one row;
  an empty grouped input returns no rows. Nonaggregate output/HAVING/order fields
  must appear in GROUP BY.
- `DISTINCT` / `РАЗЛИЧНЫЕ` removes duplicate output rows; aggregate arguments
  can also use DISTINCT. GROUP BY, DISTINCT and joins share `casefold_v1` string
  equality. The retained spelling of equivalent strings is unspecified.
- `IS NULL`, `IS NOT NULL` / `ЕСТЬ NULL`, `ЕСТЬ НЕ NULL` identify unmatched
  LEFT JOIN values. Ordinary comparisons involving Null do not select a row.
- ORDER BY admits projected aliases and aggregates in relational queries.
  ASC places Null first; DESC places it last. DISTINCT order expressions must
  be projected. TOP applies after joins, filtering, grouping, HAVING, DISTINCT
  and ordering. Rows without an explicit order have no promised ordering.

SUM/AVG require Number fields. MIN/MAX admit String, Number and Date, not Boolean
or references. Reference equality retains database/catalog identity and cannot
compare values from another interpreter metadata snapshot. SUM accumulates exact
Decimal values with the input scale; AVG rounds once to ten decimal places using
half-even rounding. Both use an owned Decimal context and bounded 38-digit output
metadata. These numeric precision rules are an explicit **host contract**, pending
native measurement. No float conversion or ambient Decimal-context rounding is used.

Scalar-only results support the existing typed `Unload` ValueTable, including
Null from LEFT JOIN or empty aggregates. Dynamic-reference projections retain
cursor support; their `Unload` remains explicitly unsupported. No query writes,
implicit casts, SQL passthrough, arbitrary functions,
nested aggregates, correlated/scalar subqueries, RIGHT/FULL/CROSS JOIN or
native regional collation are added. Section line numbers and owner dereferencing
remain outside the profile; joining the owner is the explicit supported route.

## Storage boundary and execution

`relational_queries.py` uses only the logical `CatalogReadView`: schema lookup,
`scan_catalog_values`, `scan_catalog_section`, and close. All sources are read
sequentially through **one transaction snapshot**, respecting the port's one
active continuation. Only required owner scalar fields are loaded; section rows
retain the existing full-value validation. No SQLite handle, raw SQL or physical
table name reaches the executor. A future backend can implement the same port;
PostgreSQL/MongoDB adapters are not part of this change.

An equality term across a join boundary enables a hash join; residual ON predicates
are still evaluated. Other comparisons use a bounded pair scan. Plain pre-existing
single-source queries retain their optimized typed backend scan path.

Limits: eight sources, 10,000 rows per source, 100,000 total loaded scalar cells,
8,000,000 total loaded string characters, 10,000 intermediate join rows and
1,000,000 examined pairs per join; existing projection/result bounds also apply.
Input overflow fails rather than producing an incomplete aggregate. TOP does
not bypass complete-input admission or silently turn a partial sum into success.
All read views are closed before returning or raising; executing a query never
writes data or leaves a transaction open.

## Verification and remaining work

`tests/test_relational_queries.py` covers complete BSL calls, cursor and Unload,
reference/self/chained joins, unmatched rows, grouping and HAVING, distinct values,
empty aggregates, exact decimals, owner/section/category reports, database reopen,
one-view snapshots and an independent in-memory implementation of the read port.
The existing scalar and section query suites remain regression checks.

These tests are local reference-model evidence. No native scenario, historical
fixture or evidence gate is weakened or relabeled. The existing Query24 native
observations establish only their earlier scalar slice. Native relational
observations and detailed parity calibration remain future work; do not interpret
this functional host increment as full native query certification.

[Computed expressions](computed-catalog-queries.md) add arithmetic, CASE, ISNULL,
parameters/literals and conditional aggregation to this relational profile.

[Query packages and temporary tables](query-packages-temporary-tables.md) allow
materializing and reusing intermediate report results.

[UNION and typed external ValueTable sources](query-unions-external-sources.md)
combine these reports with caller-provided scalar data and temporary stages.

The later [membership-filter block](query-membership-filters.md) adds NOT,
BETWEEN and IN, including bounded uncorrelated membership SELECTs with three-valued predicates.
