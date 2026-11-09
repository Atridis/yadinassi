# Query packages and temporary tables

Multi-step reports can materialize a filtered or computed result, then join,
filter and aggregate it again. Temporary tables live only in interpreter memory;
they do not create SQLite tables or alter the application's persistent schema.
The existing [computed query](computed-catalog-queries.md) and
[relational report](relational-catalog-queries.md) operators work over these inputs.

```bsl
Manager = New TempTablesManager;
Q = New Query;
Q.TempTablesManager = Manager;
Q.Text = "SELECT Category, SUM(Amount * &Rate) AS Total
|INTO CategoryTotals
|FROM Catalog.Products
|GROUP BY Category;
|SELECT C.Code AS Category, T.Total
|FROM CategoryTotals AS T
|JOIN Catalog.Categories AS C ON T.Category = C.Ref
|ORDER BY T.Total DESC";
Q.SetParameter("Rate", 1.2);
Results = Q.ExecuteBatch();
Report = Results[1].Unload();

Q.Text = "DESTROY CategoryTotals";
Q.Execute();
Manager.Close();
```

This example assumes Products has a numeric Amount field and a Category reference
to Categories. All catalog inputs are saved database values, not object buffers.

## Language and BSL surface

- Separate statements with semicolons; a trailing semicolon is accepted. A
  semicolon inside a quoted string remains part of that string.
- `SELECT ... INTO Name FROM ...` / `ВЫБРАТЬ ... ПОМЕСТИТЬ Имя ИЗ ...`
  materializes the projected result. Creating an existing name fails explicitly.
- A bare source name such as `FROM Prepared AS P` reads a temporary table.
  `Catalog.Name` / `Справочник.Имя` still denotes a persistent catalog. Temporary
  names, aliases and output columns use the existing case-insensitive policy.
- `DESTROY Name` / `УНИЧТОЖИТЬ Имя` drops a temporary table. A missing name fails.
  Destroying and recreating a table in the same package is supported.
- `Query.ExecuteBatch()` / `Запрос.ВыполнитьПакет()` returns an Array of statement
  results. `Execute()` / `Выполнить()` executes the complete package and returns
  its last statement result. Existing single SELECT behavior is preserved.
- `New TempTablesManager` / `Новый МенеджерВременныхТаблиц` creates an explicit
  manager. Assign it to `Query.TempTablesManager` / `МенеджерВременныхТаблиц` to
  share temporary tables across Query objects within one interpreter snapshot.
- `Close()` / `Закрыть()` frees the manager's tables. Repeated Close is harmless;
  a closed manager cannot execute further queries. Assign Undefined to detach
  it from a Query. The manager is not serializable.

Without an explicit manager, an execution gets a private manager discarded when
that execution ends. Repeating the same package therefore starts with no tables.
With an explicit manager, a later query sees previously committed temporary rows,
not changes subsequently written to their original catalogs.

## Explicit host result contract

Every package position returns a QueryResult. SELECT INTO returns a single row
with a Number `Count` column containing the number of materialized rows. DESTROY
returns an empty, zero-column result. Ordinary SELECT returns its normal detached
cursor/typed scalar Unload result. These command-result shapes and temporary-table
lifecycle rules are a bounded **host functional contract**, not measured native
1C parity. They are documented rather than inferred from historical Query24.

## Atomicity, snapshot and type boundaries

The package parses before execution. Temporary-table changes are staged and only
published to an explicit manager when every statement succeeds. Syntax, type,
resource or execution failures leave the manager as it was before the package,
including tables destroyed earlier in the failed package. This is an in-memory
package guarantee, not a persistent database transaction/write API.

All catalog reads in one package share one logical CatalogReadView snapshot;
read views close on success and failure. Temporary-only packages do not open a
database read view. The executor continues to use the logical read port, not SQL
or backend table names.

Materialized columns retain scalar kinds and qualifiers, NULL values, and catalog
reference identity even when a table has no rows. Temporary references therefore
join only to the correct catalog in the same interpreter metadata snapshot.
BSL-created managers belong to their creating interpreter metadata snapshot
and cannot be used across interpreter snapshots. A direct Python manager with no
owner binds on its first successful execution. Dynamic-reference
projections retain cursor support but their Unload limitation remains unchanged.

Results are detached. Destroying a source table or closing a manager does not
invalidate an already returned result.

## Bounds and deferred features

A package admits at most 32 statements and a manager at most 16 tables. Each
temporary table admits at most 10,000 rows. Manager and package output budgets
are 100,000 scalar cells and 8,000,000 string characters. Existing per-query
projection, source, join-work and expression-depth limits continue to apply.
Resource overflow fails explicitly; materialization must not silently turn a
partial scan into a successful intermediate table.

The [UNION and external source extension](query-unions-external-sources.md) adds
combined report sets and typed scalar ValueTable inputs. Arbitrary subqueries,
temporary indexes, query writes, documents and registers remain out of scope. It does not
change native integration scenarios or lower evidence gates. Native measurement
of package command results and lifetime details remains future calibration.

`tests/test_query_packages.py` covers multi-stage catalog/section reports, typed
Unload, reference joins over empty tables, manager isolation, failure rollback,
one-view snapshots, no-backend temporary-only execution and resource limits.
