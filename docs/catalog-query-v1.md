# Bounded catalog queries

This candidate adds `Query` / `Запрос` over the active SQLite catalog backend.
It is an object-semantic read operation, not a SQL execution API. The same port
can be implemented by future backends without exposing their connections or
query text to applied objects. PostgreSQL and MongoDB are not implemented here.

```bsl
Q = New Query;
Q.Text = "SELECT P.Code AS Item, P.Amount FROM Catalog.Products AS P WHERE P.Amount >= &Minimum ORDER BY P.Amount DESC, P.Code ASC";
Q.SetParameter("Minimum", 20);
Rows = Q.Execute().Select();
While Rows.Next() Do
    Message(Rows.Item);
    Message(Rows.Amount);
EndDo;
```

Run applied scripts with `--f EXISTING.sqlite`. Plain script execution without a
database flag still does not open or create a database. Queries cannot activate
an inactive configuration archive or bypass catalog/schema admission.

## Initial language and objects

- One `Catalog.Name` / `Справочник.Имя` source, optionally `AS` / `КАК` alias.
- Explicit standard/custom field projections with optional output aliases.
- `WHERE` / `ГДЕ`: field comparisons `=`, `<>`, `<`, `<=`, `>`, `>=`, joined by
  `AND` / `И`, `OR` / `ИЛИ` and parentheses. Operands are typed parameters or
  bounded string, number and Boolean literals. Date/reference values use parameters.
- `ORDER BY` / `УПОРЯДОЧИТЬ ПО` field lists with `ASC` / `ВОЗР` or `DESC` / `УБЫВ`.
- `TOP` / `ПЕРВЫЕ` from 1 to 10,000.
- `Text`, `SetParameter`, `Execute`; result `IsEmpty`, `Select`, `Unload`;
  result selection `Next` and projected field access, with Russian aliases.

Joins, expressions/functions, grouping/aggregates, subqueries, packages, temporary
tables, `NOT`, query writes and arbitrary SQL are refused, not approximated.
`Result.Columns` is currently unsupported. Cursor fields require a positioned row;
actual native before/after-position behavior is being measured separately.

`Unload` creates a fresh mutable ValueTable with scalar column descriptions and
qualifiers. Changing it does not write the database or mutate an earlier result.
Reference projections work through the cursor, but unloading a projection that
contains references is explicitly unsupported until truthful dynamic reference
column descriptions are implemented. No untyped stand-in is returned.

## Exact values, snapshots and limits

Numbers remain exact Decimal values; no float or SQLite numeric coercion is used.
Boolean and date comparisons require their exact logical types. References retain
database/catalog identity; a foreign-database or wrong-target parameter refuses.
No implicit cross-type conversion or Null/Undefined predicate semantics is claimed.

Each execution consumes pages from one pinned read view, closes that view, and
returns detached result rows. Parameters are bound for that execution; subsequent
parameter changes do not modify an already returned result. Internal continuation
handles are not BSL-visible, cannot switch snapshots and are not SQL cursors.

Effective admission bounds include 10,000 source records, 1,000 cards/page,
64 predicate nodes/depth 8, 16 order terms, 128 projected columns, 100,000 result
cells and 8,000,000 result string characters. Same-snapshot source-byte preflight
also applies before row materialization; details are in
[the backend contract](sqlite-catalog-backend.md). A resource refusal is not a
truncated successful result. Exact catalog lookup also no longer depends on the
ordinary first-1,000 selection limit.

String comparison/order uses the current backend's explicit Unicode code-point
contract. Native string rules depend on regional database settings; general native
collation equivalence is **not** claimed. Record identity is a backend-only stable
tie breaker, not a promise about native unspecified order. Reference range
predicates are not admitted. Do not rely on unspecified query row order.

## Evidence boundary

Local tests cover the parser, canonical typed scan, pagination, lookup beyond 1,000
rows, cursor/reference scopes and scalar unload. The separate `catalog-query-behavior-v1`
lane installs an owned XML configuration through official platform tools and runs
24 bounded scalar observations in one native action session. It does not inspect
native database files. Regional string equality, cursor boundaries and column
qualifiers are observations to verify, not hardcoded native goldens.

The SQLite comparison is labelled `owned-catalog-query-logical-reference-model`;
`metadata_import_parity_claimed` is false. Its authored logical configuration is
checked against the owned semantic profile; it does not silently strip unknown
properties from arbitrary imported configurations. Actual native acceptance is
pending until the exact source-bound lane completes and is independently audited.
