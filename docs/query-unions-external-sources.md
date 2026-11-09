# UNION and typed external query sources

This block composes catalog/section reads, typed ValueTable input and temporary
report stages in the existing logical query executor. It is a bounded **host
functional contract**, not measured native 1C parity. It does not emit SQL, write
the database or expand document/register support.

```bsl
Input = New ValueTable;
Input.Columns.Add("Item", New TypeDescription("String", , New StringQualifiers(8)));
Input.Columns.Add("Amount", New TypeDescription("Number", New NumberQualifiers(12, 2)));
Row = Input.Add();
Row.Item = "1";
Row.Amount = 5;

Q = New Query;
Q.SetParameter("Input", Input);
Q.Text = "SELECT T.Item, T.Amount INTO Combined FROM &Input AS T
|UNION ALL
|SELECT Code AS Item, Amount FROM Catalog.Products;
|SELECT P.Active, SUM(C.Amount) AS Total
|FROM Combined AS C
|JOIN Catalog.Products AS P ON C.Item = P.Code
|GROUP BY P.Active
|ORDER BY P.Active;
|DESTROY Combined";
Results = Q.ExecuteBatch();
Report = Results[1].Unload();
```

This example assumes Products has numeric Amount and Boolean Active fields.
It combines unsaved caller-provided scalar rows with saved catalog values. The
usual [temporary manager](query-packages-temporary-tables.md) can retain Combined
across executions if the final DESTROY is omitted.

## UNION language and output

- `UNION` / `ОБЪЕДИНИТЬ` removes duplicate complete rows. `UNION ALL` /
  `ОБЪЕДИНИТЬ ВСЕ` retains them. A chain is evaluated left to right: a later UNION
  deduplicates the complete accumulated left result, including earlier ALL rows.
- Each arm is an ordinary bounded SELECT with its own WHERE, joins, grouping,
  HAVING, DISTINCT and optional TOP. At most 16 arms are admitted per statement.
- The one optional ORDER BY follows the last arm and sorts the **whole union**.
  It accepts only unqualified first-arm output names, not source fields,
  ordinals, later-arm aliases or expressions. ORDER BY before another UNION is
  rejected. TOP remains arm-local, before this final sort; there is no global
  TOP or parenthesized arm ordering. Use a subsequent temporary-table SELECT
  for an ordered top-N over the combined result.
- An optional INTO appears only in the first SELECT and materializes the whole
  union, not the first arm. Later-arm INTO is rejected. ExecuteBatch returns one
  result for the union statement; INTO returns the existing host Count result.
- Output names and their localized/unaliased behavior come from the first arm.
  Later aliases do not rename columns. Column matching is positional, with
  exactly the same column count and compatible types even when arms are empty.

NULL-only projections are admitted inside a union if another arm supplies that
position's type. An entirely NULL-only output column is rejected. Scalar kinds
must match, with no String/Number or Boolean/Number conversion. References must
have the same catalog and interpreter metadata snapshot; this is checked before
scanning even empty sources. Reference cursors and temporary joins remain
supported, while dynamic-reference Unload remains explicitly unsupported.

Numeric metadata uses the largest scale and integer capacity, capped at 38 total
digits. Every returned number must fit the combined qualifiers exactly; overflow
fails without rounding, clipping or partial results. Nonnegative is retained
only if all typed arms declare it. String length uses the largest bound (zero
means unbounded); Fixed survives only when all typed arms have the same fixed
length. Equal Date/Time restrictions survive; mixed restrictions widen to
DateTime. These qualifiers and NULL values survive INTO and scalar Unload.

Duplicate keys use the existing relational policy: casefolded strings, exact
Decimal equality, Date ticks, distinct Boolean identity, NULL equality and full
catalog reference identity. First occurrences are retained. This is not a
regional native collation claim. Without ORDER BY, application code should not
rely on catalog scan order.

## External ValueTable sources

`FROM &Table AS T` / `ИЗ &Таблица КАК Т` reads a Query parameter supplied through
SetParameter. It works directly, in joins, in union arms and in canonical
`SELECT ... INTO Temp FROM &Table AS T`. Names are case-insensitive; the default
alias is the parameter name. External `&Name` and temporary `Name` occupy
separate namespaces.

The input must be an exact ValueTable with 1–128 uniquely named identifier
columns. Every column must have a TypeDescription for one scalar kind:

- String: Variable or Fixed, length 0–65,536 UTF-16 units. Zero is unbounded
  metadata, subject to the per-value resource bound of 65,536 characters.
  Values must satisfy the declared bound/fixed length and valid Unicode.
- Number: explicit precision 1–38, scale 0–precision and Any/Nonnegative sign.
  Unqualified Number has no bounded declared scale and is rejected. Actual
  values must be finite, exact declared numbers within qualifiers and the
  existing query numeric envelope, without coercion.
- Boolean: exact Boolean cells.
- Date: known Date values respecting Date, Time or DateTime qualifiers.
- Existing query Unload scalar-plus-NULL descriptions are accepted, including
  actual NULL cells. This does not enable public mixed-NULL TypeDescription
  construction, nullable defaults/coercion or serialization.

Untyped columns, heterogeneous type descriptions, standalone Null, UUID,
dynamic references, objects, Undefined cells and restricted register slice
tables are rejected. Empty tables still require complete valid metadata. All
cells, including unprojected columns and rows filtered away by WHERE/TOP, are
validated. Existing ValueTable assignment may already have adjusted a value;
query ingestion does not perform a second conversion or modify the input.
Indexes, column titles and display widths have no query semantics.

SetParameter retains the caller's table until execution. At each Execute or
ExecuteBatch, every referenced external parameter is validated and copied **once
before any statement/database read**. Repeated uses of that parameter in all
arms/statements see the same detached scalar snapshot. Later executions take a
fresh snapshot, while returned results and committed temporary tables remain
independent of subsequent caller edits. No table or row buffer enters a result,
and no codec or dynamic type-admission boundary is bypassed.

## Snapshot, rollback and resource guarantees

All catalog inputs in union arms and package statements share one CatalogReadView.
External/temporary-only execution opens no backend view. Views close on success
and failure. The existing package staging guarantee covers union execution:
syntax, type, qualifier, input/output resource, execution and view-close failures
publish no temporary creations or destructions.

External snapshots have a combined 100,000-cell / 8,000,000-character budget and
at most 10,000 rows per source. Repeated source reads still charge the existing
package input budgets. Union arm outputs cumulatively charge 100,000 cells /
8,000,000 characters, including duplicates. Every intermediate union result is
limited to 10,000 rows and never silently truncated; explicit arm TOP does not
bypass full-input validation. Existing package/temporary-table, expression,
projection and join-work limits continue to apply.

Tests in `tests/test_query_sources.py` cover an end-to-end BSL reporting pipeline,
bilingual grammar, mixed union duplicates, NULL/reference metadata, qualifier
promotion, ordering ownership, empty incompatible arms, detached caller inputs,
one-view reads, rollback, resource refusal and preserved scalar-query fast path.
The existing query suites remain regression coverage. No native scenario,
fixture, protocol cap or evidence gate changes; native calibration remains future
work. Arbitrary subqueries, casts, dynamic ValueTable references, temporary
indexes and query writes remain out of scope.
