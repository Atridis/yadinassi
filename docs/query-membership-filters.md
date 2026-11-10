# Typed membership filters and nested SELECTs

This is a bounded local Query contract, not a claim of native 1C parity. Query
text is parsed into the interpreter's closed AST; it is never passed to SQLite
as user SQL. Database layout and metadata admission are unchanged.

## Operators

- Prefix `NOT` / `НЕ` binds more tightly than `AND`, then `OR`. Parentheses
  group predicates. Repeated NOT is bounded by the existing nesting limit.
- `value [NOT] BETWEEN lower AND upper` / `МЕЖДУ ... И ...` includes both
  bounds. Operands require the same ordered scalar type. A reversed interval is
  empty; boolean and reference ordering is rejected before reading rows.
- `value [NOT] IN (expression, ...)` / `[НЕ] В (...)` compares a bounded list
  using exact scalar/reference types. List elements may be computed expressions
  or fields in the same scope. String comparison retains the existing casefold
  policy, not regional database collation.
- `value [NOT] IN &Values` accepts Array or FixedArray. Query captures a detached
  tuple of its scalar values once at the beginning of Execute/ExecuteBatch,
  before opening a database snapshot. Changes made before Execute are observed;
  later buffer changes do not alter any statement of that execution. Nested
  arrays, arbitrary host objects, mixed non-Null types and oversized buffers are
  rejected. Lists are not scalar operands or external table sources.
- `value [NOT] IN (SELECT ...)` accepts an uncorrelated, one-column selection.
  The inner selection can use joins, aggregates, grouping, HAVING, TOP, ordering,
  UNION, temporary tables, typed external ValueTables, documents, registers and
  admitted periodic register slices. Inner SELECTs cannot create temporary
  tables, contain statement separators, or refer to an outer alias.

These predicates compose in WHERE, ON, HAVING and CASE conditions. Correlated
subqueries, scalar subquery expressions, EXISTS, LIKE, arbitrary table
expressions in FROM and query writes remain unsupported.

## Null is unknown, not false

Ordinary comparisons with Null produce an internal unknown truth value.
NOT unknown is unknown. AND is false if either operand is false; OR is true if
either operand is true. Otherwise an unknown operand propagates. ON, WHERE,
HAVING and CASE select only a true condition. IS NULL and IS NOT NULL still
produce true or false.

For IN, a matching non-Null value gives true. With no match, an inner/list Null
makes the result unknown. Thus `Amount NOT IN (10, NULL)` selects no rows:
10 is excluded by a match and other values are unknown.
An empty array or empty subquery makes IN false and NOT IN true, including for
a Null left operand. An empty literal list `IN ()` is not part of the grammar.

## Identity, snapshots and budgets

Types and reference metadata identities are checked before source reads, even
when a source or subquery is empty. Catalog and document references keep their
snapshot/target identity; there is no implicit conversion to strings or UUIDs.

All database sources of a package, including nested SELECTs, share one logical
read view. Required document/register metadata is prepared before that view
opens. Each uncorrelated inner plan is evaluated once per statement execution,
not once per outer row. Membership sets are released with the plan; results do
not retain live cursors. Failed package evaluation does not publish temporary
tables, and owned views still close on failure.

Bounds are host resource limits: 256 expressions in a literal IN list, 10,000
values in a parameter array, 16 nested SELECT occurrences per package, nesting
depth 8 for subqueries, and the existing 32 predicate levels/128 comparisons.
Input cells, text and materialized membership values share the package's
100,000-cell/8,000,000-character budget. Membership probes/comparisons share a
1,000,000-work-unit budget. Constant lists, frozen parameters and inner results
use typed hash membership; row-dependent lists use bounded comparisons.
Exceeding a bound raises an error rather than returning partial results.

## Example

The following report requires a configuration with Products and Categories:

```bsl
Excluded = New Array;
Excluded.Add("archived");
Q = New Query(
"SELECT P.Code, P.Amount
|FROM Catalog.Products AS P
|WHERE P.Amount BETWEEN 10 AND 100
|  AND NOT P.Code IN &Excluded
|  AND P.Category IN (
|    SELECT C.Ref FROM Catalog.Categories AS C
|    WHERE NOT C.DeletionMark=TRUE)
|ORDER BY P.Code");
Q.SetParameter("Excluded", Excluded);
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Code);
    Message(Rows.Amount);
EndDo;
```
