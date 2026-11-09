# Computed catalog reports

Catalog queries can now calculate output columns, conditional totals and report
ratios over saved catalog objects and tabular sections. This extends the
[relational query profile](relational-catalog-queries.md), with no storage-format
change, implicit writes, external SQL execution or additional database family.

```bsl
Q = New Query;
Q.Text = "SELECT P.Code AS Product,
|SUM(CASE WHEN L.Amount > 0 THEN L.Amount * &Rate ELSE 0 END) AS PositiveTotal,
|ISNULL(SUM(L.Amount), 0) AS Total,
|CASE WHEN COUNT(L.Amount) > 0 THEN SUM(L.Amount) / COUNT(L.Amount) ELSE 0 END AS Mean
|FROM Catalog.Products AS P
|LEFT JOIN Catalog.Products.Lines AS L ON P.Ref = L.Ref
|GROUP BY P.Code
|ORDER BY Total DESC";
Q.SetParameter("Rate", 1.2);
Rows = Q.Execute().Unload();
```

The example assumes Products has a Lines section with a Number Amount field.
It reads persisted values from the selected database, not unsaved object buffers.

## Expressions

- Numeric `+`, `-`, `*`, `/`, unary `+`/`-` and parentheses. Multiplication and
  division bind before addition and subtraction; binary operators associate left.
- String, Number, Boolean and NULL literals, and `&Parameter` references, including
  in projected output. Computed columns require an explicit `AS` / `КАК` alias.
- Searched `CASE WHEN condition THEN expression [WHEN ...] [ELSE expression] END`.
  Russian spellings are `ВЫБОР КОГДА ... ТОГДА ... ИНАЧЕ ... КОНЕЦ`.
  The first true condition wins. An omitted ELSE produces NULL.
- `ISNULL(value, fallback)` / `ЕСТЬNULL(value, fallback)` uses the fallback only
  when the first value is NULL. It is distinct from the `IS NULL` predicate.
- Expressions compose with projections, ON, WHERE, GROUP BY, HAVING, ORDER BY
  and aggregate arguments. For example, `SUM(Amount * &Rate)` calculates each
  row before summing; `SUM(Amount) / COUNT(*)` calculates after aggregation.
- All existing joins, cursor operations, parameter rebinding, DISTINCT, TOP and
  scalar typed Unload remain available. The simple field-only scan keeps its
  existing backend path.

## Types, grouping and NULL

All names, parameters, argument types and branch types are checked before reading
source rows, including unreachable CASE arms and empty source tables. Arithmetic
requires Number; strings do not concatenate and Booleans do not become numbers.
A NULL-only projected column is rejected because it has no supported scalar
Unload type; use a typed fallback such as `ISNULL(NULL, 0)`.
CASE arms and ISNULL arguments must have compatible exact scalar types; NULL can
participate without turning a value into a different scalar type.

CASE and ISNULL evaluate only the selected branch. A dead numeric branch such as
`ISNULL(Amount, 1 / 0)` therefore does not divide by zero, but an unknown field or
an incompatible type in that branch still fails validation. Arithmetic involving
NULL produces NULL. Ordinary comparisons with NULL do not match; use IS NULL.

Aggregates are not admitted inside ON, WHERE or GROUP BY, and cannot nest inside
other aggregates. In a grouped report each nonaggregate field must be covered by
the grouping expression. Conditional aggregation uses a condition *inside* the
aggregate, for example `SUM(CASE WHEN Active=TRUE THEN Amount ELSE 0 END)`.
A row-level condition outside an aggregate must itself satisfy grouping rules.

## Numeric and resource contract

Computed Number semantics are an explicit host contract, not a claim of measured
native 1C precision. Decimal arithmetic uses its own context; caller precision,
rounding, traps and flags are not changed. Division rounds half-even to ten
fractional digits. Addition/subtraction keep the larger operand scale; multiplication adds operand
scales. Conditional expressions use the largest branch scale. Computed values
and typed Unload metadata are bounded to 38 decimal digits. Overflow and live division by zero fail explicitly rather
than returning a clipped or nonfinite value.

The existing source, intermediate-row, scalar-cell, string, result and join-work
limits still apply. Expression and condition nesting is bounded to 32 levels, including long
left-associated arithmetic chains. TOP is applied
only after the complete admitted report; it cannot conceal overflow in a required
aggregate input. Read snapshots close on both success and failure.

## Verification and boundaries

`tests/test_computed_queries.py` covers English and Russian syntax, precedence,
parameters, conditional and distinct aggregates, grouping, joins, NULL handling,
BSL cursor/Unload calls, reopened databases, static error checks, decimal-context
isolation and resource failures. Existing catalog/section/relational query tests
remain regression coverage.

This is local host-functional evidence. No integration scenario, native fixture,
or evidence gate is changed. Existing native Query24 observations cover their
original scalar slice, not these new expressions. Detailed native calibration,
additional scalar functions, casts, date/string arithmetic, subqueries, UNION,
temporary tables, query packages, documents and registers remain future blocks.
