# Derived query sources and outer joins

This is a bounded, typed local reporting contract, not a native 1C parity claim.
A FROM or JOIN source may be an uncorrelated SELECT or UNION in parentheses.
Every derived source requires an explicit `AS Alias` / `КАК Псевдоним`.

```bsl
Q = New Query(
"SELECT D.Number, ISNULL(L.Total, 0) AS Total
|FROM Document.Orders AS D
|LEFT JOIN
| (SELECT Ref AS Owner, SUM(Amount) AS Total
|  FROM Document.Orders.Lines GROUP BY Ref) AS L
|ON D.Ref = L.Owner
|ORDER BY D.Number");
S = Q.Execute().Select();
While S.Next() Do
    Message(S.Number);
    Message(S.Total);
EndDo;
```

## Scope and types

Derived selections can contain further derived sources, admitted joins,
GROUP BY/HAVING, aggregates, computed expressions, DISTINCT, TOP, ORDER BY,
UNION, membership subqueries, temporary tables, typed external ValueTables,
catalogs, document sections and independent/periodic register sources.
Inner ordering and TOP apply before outer filtering and ordering. No output
order is promised without the applicable ORDER BY.

The outer query sees only the derived output columns. Use explicit output
aliases when stable names matter: the existing `Code` projection without AS
may be localized to `Код`. Names must be unambiguous and case-insensitively
unique. An outer alias is not visible inside a derived query. Correlated
sources, LATERAL, scalar subquery expressions, EXISTS, LIKE and CROSS JOIN
remain unsupported. A derived source cannot contain INTO, DESTROY or a package.
An outer statement may put its derived result INTO a temporary table.

The output schema is determined before reading, even when a source is empty.
Numeric/string/date qualifiers and reference metadata identity are retained.
Reference columns remain usable for equality and cursor values; dynamic
reference Unload is still closed. Scalar Unload remains typed and can contain
Null from an outer join. A Null-only derived column needs a typed branch or
UNION arm; it cannot invent a metadata type.

## RIGHT and FULL joins

`RIGHT [OUTER] JOIN` / `ПРАВОЕ [ВНЕШНЕЕ] СОЕДИНЕНИЕ` preserves every row from
the right source. For unmatched right rows, all prior left sources become
Null. `FULL [OUTER] JOIN` / `ПОЛНОЕ [ВНЕШНЕЕ] СОЕДИНЕНИЕ` also preserves
unmatched left rows. ON / ПО is mandatory. Duplicate rows keep their
multiplicity; each physical right row is tracked independently.

Only an ON predicate that evaluates to True is a match. False and unknown
are not matches, including Null = Null. WHERE runs after join expansion,
so a WHERE predicate on the nullable side can remove an unmatched row.
Grouping, COUNT(*) and COUNT(field) retain their existing Null semantics.

## Snapshot, ownership and bounds

All persistent sources in one query/package, including nested derived and
membership sources, share the same logical read snapshot. Document/register
metadata is initialized before that snapshot opens. External tables and list
parameters use the existing once-per-package snapshots. Derived results are
materialized once for that source occurrence; they are not re-executed per
outer row. No user SQL or physical table names reach SQLite.

Parsing shares the limit of 16 nested subqueries and depth 8 between derived
and membership sources. Each SELECT retains at most eight sources and 128
output columns; existing text/token/package/UNION bounds still apply.
Input and materialized derived cells/text count toward the shared resource
budget, including columns not projected by the outer query. Row limits do not
silently truncate source aggregates. JOIN candidate work shares a cumulative
1,000,000-pair cap across nested plans, UNION arms and package statements;
intermediate join rows remain limited to 10,000. Equality joins use an index
and still evaluate residual ON predicates.

Failure returns no partial result, does not publish temporary tables, and
closes the owned snapshot. These bounds and casefold string comparisons are
local implementation rules, not native regional collation or native limits.
