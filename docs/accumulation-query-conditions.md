# Explicit stock query conditions

This block adds typed dimension parameters to the existing Balance, Turnovers
and BalanceAndTurnovers sources. It does not add SQL, UI reports, a storage
format, migration, write authority or automatic WHERE pushdown.

This page describes the original reference-profile contract. Exact format16 has
a separate [typed scalar/reference/enum condition grant](typed-virtual-dimension-predicates.md).
The older profiles do not acquire that grant implicitly.

```bsl
AccumulationRegister.Stock.Balance(&At, Product=&Product AND Warehouse=&Warehouse)
AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,, Product=&Product)
AccumulationRegister.Stock.Turnovers(&StartAt,&EndAt,Month, Warehouse=&Warehouse)
AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt,,, Product=&Product)
AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt,Day,, Product=&Product AND Warehouse=&Warehouse)
```

Dates remain required named parameters. Periodicity is the existing literal
Day/Month subset. The fourth combined-table slot is the empty, default completion
method, not a new completion-mode grant. Blank trailing optional slots are accepted.
Russian virtual names, AND and periodicities are supported. Conditions contain
only unqualified declared CatalogRef dimensions, equality to named parameters,
parentheses and AND. At most 16 terms are admitted within the existing overall
query predicate budget. OR, IN, scalar/resource conditions, outer-alias references,
expressions, explicit completion modes and omitted date boundaries remain closed.

Parameters must be exact references issued by the current interpreter's catalog
family for that dimension. Wrong catalog, foreign database/family, forged metadata
or callbacks are refused before an ordinary query opens its lease. There is no
wrong-target assignment coercion, code/UUID-string conversion or existence-cache
lookup. A genuine missing GetRef or typed EmptyRef matches no stored occurrence;
it never means “all”. Reference-bearing Unload remains unsupported.

## Grouping and empty results

The new explicit-condition surface groups by the dimensions actually referenced
by the query, including SELECT expressions, WHERE, ON, GROUP BY, HAVING and ORDER
BY. A dimension used only inside the virtual condition is not an output grouping
dependency. Thus a resource-only Balance filtered by Product can return one sum
across warehouses. Include Warehouse in the query to obtain separate rows. A
resource-only nonperiodic Balance or combined statement with no matching input
returns one qualified zero-resource row. Turnovers remains empty. No reference or
calendar bucket is invented for missing input.

Legacy unconditioned sources keep their existing full-schema grouping/admission.
Blank optional slots alone do not switch them to the new explicit-condition path.
Ordinary WHERE still runs after reduction. In addition to native-compatible
syntax, explicit scoping avoids materializing or adding unrequested groups. It
does not bypass malformed source rows, physical/input limits or reference checks.
This is not a claim that every legacy WHERE query is natively equivalent.

All physical source rows and all fields are validated and charged before the
condition excludes an occurrence. Dependency grouping and numeric reduction then
use the existing exact arithmetic and date rules. Generated output and zero rows
remain bounded. One actual owner snapshot covers joins/derived sources/packages,
including borrowed writer reads; no new connection, cache or SQL index is added.
Each package statement still binds in sequence under the existing package contract.

## Evidence and limits

Independent native acquisition
[43070878852](https://github.com/Atridis/yadinassi/actions/runs/43070878852)
captured all twelve groups on 1C 8.3.27.1508. Installation, material redump, 42
input/host hashes, source tree and cleanup were verified. Its immutable capture
is `tests/fixtures/native_inventory_filter`. Groups 1 and 9 establish the
dimensionless aggregation and zero-result behavior above; groups 3–8 include the
blank-slot controls and Day/Month results. Groups 10–12 cover residual aggregation,
JOIN/derived/package composition and staged write/rollback/repost.

The acquisition report correctly says `runtime_parity_accepted=false`: native
capture alone is not a host replay. Local replay and security/budget regressions
are separate gates. No wider completion/calendar/scalar-filter behavior is inferred.
The 1900–2099 combined/periodic date envelope remains an explicit host limit,
not a native calendar boundary. Existing source profiles and physical14/15 are unchanged.

## Fresh CLI scenario

Use a new file with the existing inventory source profile, seed its supported stock
documents, then run three parameterized read-only reports in one query package:

```console
python -m yadinassi --create-demo-db scoped-stock.sqlite --import-xml examples/demo
python -m yadinassi --f scoped-stock.sqlite examples/inventory_reference/period_seed.bsl
python -m yadinassi --f scoped-stock.sqlite examples/inventory_reference/scoped_statement.bsl
```

The final command selects PS-STOCK at PS-W and shows balance10, January turnover7,
March turnover−2, and the corresponding monthly opening/receipt/expense/closing
statement. It does not post, unpost or mutate objects. It does not migrate an older
demo file or duplicate the separately granted UI report/filter/page surface.
