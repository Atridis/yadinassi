# Direct enum inventory reports

This query extension belongs only to explicit `inventory-enum-v1` (physical16).
It adds one direct Execute with enum `IN (&Values)` / `NOT IN (&Values)`,
one-column uncorrelated membership SELECT/UNION, homogeneous enum CASE/ISNULL,
and internal derived SELECT/UNION/UNION ALL. No storage format, migration,
forms grant or posting authority is added. Formats14/15/forms15 keep their
previous query admission.

`examples/inventory_enum/seed.bsl` creates a posted receipt and a pending receipt
in a fresh enum fixture database. `relational_report.bsl` combines actual stock
with pending lines, fills absent stock from the product's enum unit, filters
selected units and groups the combined report. It uses a typed cursor, not
reference-bearing Unload. Create the database explicitly from
`scripts/inventory_enum_relational_behavior/runtime_source` with
`--create-db --import-xml ... --source-profile inventory-enum-v1`; do not import
this source into an existing demo or infer a migration.

Пользовательские скрипты выполняются в основной базе `examples/demo`, а не в
отдельной enum-конфигурации. Создайте её обычным `--create-demo-db ... --import-xml examples/demo`,
затем запустите `seed.bsl` и `relational_report.bsl` из `examples/inventory_enum`.
Единица хранится в строке документа; у исходной Номенклатуры нет поля Unit,
поэтому отчёт явно передаёт `DefaultUnit`, не добавляя выдуманное поле в каталог.
Исторический native replay ниже остаётся на своих неизменных source hashes.

## Closed contract

Each Execute freezes exact Array/FixedArray buffers once. The direct16 bound is
256 members per parameter, including unused parameters and duplicates. Every
enum member must belong to the current canonical issuer. Catalog parameters
retain exact type, metadata and bound-callback ownership checks; there is no
existence lookup. Existing shared input, intermediate, join, membership, cell,
text, parser and stock validation budgets remain in force before deduplication
or filtering. Legacy global array limits are unchanged.

Array membership requires parentheses. A single parenthesized scalar parameter is admitted only as an owned enum
singleton or the separately supported NULL absence, not as an Array. Measured
owned other-enum values are nonmatches. The measured String/Number wrong-kind
controls apply to Array members only; String/Number scalar singletons remain
refused. No query input uses assignment-to-empty conversion. Other reference,
Boolean and Date membership kinds remain refused. NOT is admitted only directly
over membership; other NOT expressions remain closed in this direct16 surface.
NULL parameters are scalar absence in exact16 only; typed-empty enums are
ordinary domain members and remain distinct from NULL.

For measured enum Array and subquery membership, a NULL RHS item does not poison
NOT IN for a non-NULL probe. Original RHS cardinality is retained separately:
an empty list is not a nonempty NULL-only list. No scalar/catalog/document
membership rule in other profiles is changed by this enum-specific branch.

Canonical immutable descriptors are issued per Execute and carried through
internal columns. Mixed enum output domains are refused before scanning,
including empty arms and unselected CASE branches. NULL alone cannot invent an
enum domain. All derived, UNION and membership sources share one actual owned
read view; namespace liveness is rechecked within it, even for empty results.
Results are detached data, not a lease or durable issuer capability.

Persistent packages, INTO/DESTROY, TempTablesManager, external tables,
correlated queries, enum ordering/MIN/MAX, mixed-enum output descriptors and
reference Unload remain closed. No generic package refusal is removed.

## Measured subset, not full observer parity

Independent native run43119374440 used source commit
`0b481c58488b84f326fa81f5036b4d3eb5dc137b`, tree
`d81e471823a408ac4d4daec1ba09cb1934b29fdc`. The immutable raw capture has12 groups
and79 sub-controls, with source/module/material-redump/nonce and cleanup proofs.
`tests/fixtures/native_inventory_enum_relational/supported-controls.json`
maps each exact fragment to71 value comparisons,2 measured syntax refusals
and6 intentional host refusals of wider native compound outputs. The unchanged
observer host replay passed this supported projection in normal and optimized
Python; it does not convert wider native acceptance into a parity claim.
It does not rewrite native acceptance into refusal or claim full12 byte parity.
Host replay is a separate implementation gate, not an acquisition flag.

Row labels witness actual emitted value types. Empty or NULL-only results do
not prove declared column metadata. Array mutation is measured before/between
Execute, not during materialization. Cross-family/forged/stale ownership,
one-view sharing, resource limits and cleanup faults require host regressions.

The native Bound helper sets a scalar NULL parameter, but no query expression
uses that parameter. NULL-parameter operator behavior is an explicit host
contract checked by regressions, not a separately measured native control.
