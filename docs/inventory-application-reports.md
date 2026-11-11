# Bounded inventory application reports

`InventoryReports(context, configuration)` is a trusted, read-only host adapter
for the exact `InventoryApplicationConfiguration` / physical-15
`accumulation-reference-forms-v1` grant. Raw core15, scalar accumulation14,
posting13 and other profiles remain denied. It does not install BSL names,
execute a form/handler, create a root token, open a journal or resolve a receipt.

## Closed API

```python
reports = InventoryReports(context, configuration)
movements = reports.read("StockMovements")
balance = reports.read("StockBalance", at=boundary)
turnovers = reports.read("StockTurnovers", start=first, end=last)
```

The example names are not hardcoded. The exact name must be present in the
canonical full-source manifest and binds the exact register name/UUID and one
of `Movements`, `Balance`, `Turnovers`, or the explicit statement extension
below. No SQL, BSL, arbitrary expression,
projection, order, register identifier, callback or browser-selected key is
accepted. Dates must be exact naive Python `datetime`, second-resolution, with
`fold=0`. Missing, surplus or reversed boundaries are refused:

- Movements accepts no bounds and retains every active occurrence, including
  repeated identical lines. Resources keep their stored unsigned-by-direction
  values; `RecordType` is the exact `AccumulationDirection` enum.
- Balance uses `Period < at`, omitting all-zero net groups.
- Turnovers uses `start <= Period <= end`. Each resource produces net Turnover,
  Receipt and Expense totals. Expense is the sum of stored expense resources,
  not a sign-flipped presentation. All-zero turnover groups remain outside the
  existing measured aggregate subset and are refused.

Aggregation reuses the existing exact scaled-integer resource arithmetic and
38-digit result checks. It does not round/truncate, depend on ambient Decimal
precision, or introduce new native semantics. String dimensions use the existing
caseless UCA grouping key. Reference dimensions use database/catalog/record
identity, not labels. Movements sort by period, document UUID, record UUID and
line number. Totals sort by typed dimension keys; string-equivalent groups retain
the first representative in the storage port's deterministic recorder/line order.
This is a bounded host report order, not native UI sorting parity.

## One snapshot and immutable result

Every successful read uses one `begin_read` lease. That begin validates actual
stored source bytes/hashes, schema, profile and identity. The report additionally
reimports the full source/manifest marker on that same connection before scanning
movements. It compares against the constructor's pinned configuration and
DB/generation binding. Neither generation alone nor a temporary core projection
is sufficient. No second source export, document lease or presentation connection
is opened. Concurrent/new business state is seen only on a subsequent read.

`InventoryReportResult` is frozen and contains:

- `database_id`, `configuration_generation`, `source_digest`;
- manifest `report`, `register_id`, `register`, `view`, and typed `boundaries`;
- `columns: tuple[InventoryReportColumn, ...]`;
- `rows: tuple[tuple, ...]` with immutable exact host values;
- `labels: tuple[(CatalogKey | DocumentKey, str), ...]`.

Columns expose `name`, `kind`, `qualifiers`, `field_id`, `role` and optional
`target_catalog_id`. The identity of a declared column is `(field_id, role)`, not
its display name; a schema can have a dimension whose name resembles a derived
resource label. Raw standard columns are Period, Recorder, LineNumber, RecordType,
Active, followed by dimensions/resources/attributes in admitted schema order.
Totals contain dimensions, then all resources for each suffix in order.

CatalogKey and DocumentKey remain exact internal typed identities; no runtime
reference, BSLDate, VM, cursor or connection escapes. Dates are Python datetime;
numbers are Decimal. Presentation is read under the same lease: catalog
Description, falling back to Code, and recorder metadata name + Number + Date.
Each distinct returned key is looked up once. Empty/missing presentation records
and deletion-marked records show `[Unavailable record]`. A dangling nonempty
movement reference already violates the core port's integrity contract and fails
the report rather than being disguised as a successful placeholder result.

The controller must map report grants and render labels without exposing or
accepting persistent keys/UUIDs as browser authority. Labels are plain text,
never HTML. This module does not implement a wire codec.

## Bounds, failures and receipt fences

Fixed limits are 10,000 input occurrences, 100,000 input cells and 1,000,000 text
characters. Every source row/cell is charged before period exclusion. The existing
storage port also enforces its database, partition and payload bounds before
materialization. Output is limited to 1,000 rows / 25,000 cells, 2,000 distinct
labels and 1,152 characters per label. Output strings plus labels share the text
limit. A controller's existing transport byte limit may refuse an otherwise
valid report earlier. Limits refuse the entire result; there is no implicit
pagination, partial success or truncation.

The service refuses BSL activation, denied child admission and registered
transaction owners. It never borrows a writer's uncommitted state or clears a
foreign/uncertain owner. Busy, corrupt, replaced, closed or changed sources fail
closed. Lease cleanup happens before a result is returned, also on interruption.

Detached root receipts are retained by the application host, not discoverable
from this backend. The controller must retain its pending_commit/pending_refresh
fences and not call reports while an affected operation requires resolution or
authoritative refresh. A read is not a resolution attempt and is never evidence
that an uncertain write rolled back or committed. It cannot unlock a form, replay
a handler or make a host-lifetime receipt durable after restart.

Tests in `tests/test_inventory_application_reports.py` cover real owned SQLite
profiles, posted/undo state, exact aggregates and identities, one-lease label
reads, tamper and source binding, budgets, owner refusal and cleanup. Test results
are reported separately; source documentation is not native/browser evidence.

## Source-declared stock statements

The same exact forms15 grant can explicitly declare `BalanceAndTurnovers`.
This does not grant reports to core15, format14 or format13. The old three report
shapes retain their previous behavior and reject statement-only options. A
statement declaration is a closed opt-in within the full hashed source:

```xml
<Report name="StockStatement" register="Stock" registerId="REGISTER-UUID"
        view="BalanceAndTurnovers">
  <Periodicity name="None"/>
  <Periodicity name="Day"/>
  <Periodicity name="Month"/>
  <Filter dimension="Product" dimensionId="DIMENSION-UUID" catalogId="CATALOG-UUID"/>
</Report>
```

The UUID placeholders above must be the exact canonical identities from the
admitted metadata, not fresh IDs or browser input. The example source uses real
identities. Names are not hardcoded by the service. One to three distinct
`Periodicity` children precede zero to sixteen unique `Filter` children. Only
`None`, `Day`, and `Month` are supported, with exact case; filters must bind
catalog-reference dimensions by name, dimension UUID and target catalog UUID.
Unknown attributes/children, duplicate options, mixed content, or options on an
old report are refused. `InventoryReportGrant` adds immutable `periodicities`
and `filters`; each `InventoryReportFilterGrant` contains `dimension`,
`dimension_id`, and `catalog_id`. Old grants have empty tuples for both fields.

```python
selection = InventoryReportFilter(dimension_id, exact_catalog_key,
                                  configuration_generation)
statement = reports.read("StockStatement", start=first, end=last,
                         periodicity="Month", filters=(selection,))
```

`periodicity` is mandatory for a statement and must be source-granted. Omitted
`filters=()` means all dimensions. Each supplied filter is an exact frozen
`InventoryReportFilter`, not a string, runtime object, label or browser UUID.
Its dimension must be granted, its exact CatalogKey must have the same database
and target catalog, and its exact integer generation must match this service's
pinned generation. Duplicate dimensions and mutable/subclass inputs are refused
before opening a lease. Filter ordering in the result follows the source grant,
not caller ordering. The controller must issue and validate any browser selection
capabilities separately; this trusted host API does not deserialize them.

An explicit empty CatalogKey filters only empty references; it is not the same
as omitting the filter. It has the unavailable label and requires no nonexistent
card lookup. Nonempty selected cards are read under the report's single lease:
missing cards refuse the read, while deletion-marked historical cards remain
selectable read-only and have `[Unavailable record]` presentation. Neither case
confers any write or object-form authority. Selected labels remain in the result
even when no movements match, and share all output label/text limits.

Statement input bounds are exact naive whole-second datetimes in **1900–2099**,
with start no later than end. This is an explicit host/UI request envelope, not a
restriction on the core calendar. Older stored movements are still charged and
can contribute to the opening balance; they are never silently dropped.
Opening is strictly before start; receipts and expenses include both endpoints;
closing incorporates opening and those flows. The verified pure
`accumulation_periods.StatementReducer` owns all statement arithmetic and sparse
calendar behavior. No second evaluator, Query string, connection or duplicated
aggregation algorithm is introduced.

None yields one nonzero vector per dimension group and no Period column. Day
and Month add a typed Period after the dimensions. The first bucket label is
clipped to the requested start. The reducer emits observed flow buckets and
nonzero opening/closing boundary buckets, not dense gap filling. All-zero
statement vectors are omitted without poisoning other groups. Output order is
exact typed dimension identity followed by period. Columns then contain every
resource for each suffix in this order: `OpeningBalance`, `Receipt`, `Expense`,
`ClosingBalance`. Roles are the lowercase suffixes; resource field UUIDs,
38-digit exact result checks, and declared decimal scales are retained.

`InventoryReportResult` additionally contains `periodicity` and a frozen `filters`
tuple; old reports use `None` and `()`. Its rows, labels and filter identities are
fully detached after successful lease cleanup. Every source occurrence/cell/text
is charged before either date or dimension filtering. Sparse output expansion
shares the existing 1,000-row / 25,000-cell caps and refuses the entire result
rather than truncating. A separate UI adapter may page this retained immutable
result using scoped opaque cursors; the service never re-reads a later database
snapshot to fetch another page. Pending receipt fences remain the controller's
responsibility and are not bypassed by filtering or pagination.

Targeted statement tests live in `tests/test_inventory_application_statements.py`;
the earlier source and report tests remain applicable. Documentation describes
the contract, not a claim that this new integration has already been executed.


### Browser statement setup and detached pages

The separate statement UI asks the trusted host to prepare source-declared
filters. Choose a saved Product or Warehouse by exact code, explicitly choose
an empty reference, or select All to omit that filter. Cancel keeps the previous
selection. Browser labels and opaque choice tokens are not persistent keys;
selected keys are revalidated by the final report read in its own admitted
snapshot. A missing nonempty card is refused. Historical deleted references are
read-only, unavailable presentations, not writable objects.

Statement results are sealed after the complete bounded read. At most 1,000
rows / 25,000 cells are retained, with at most 50 whole rows per page and a
64-KiB encoded page budget. An oversized row or snapshot refuses the entire
result, never truncates successful output. Previous and Next navigate that
same detached snapshot without rereading SQLite or resolving a posting receipt.
Refresh explicitly to observe another writer. Form activity, a different filter
setup, and shutdown retire page cursors; an old response cannot target a new
selection or snapshot. Opaque cursors are host-lifetime only.

Report controls form an external UI action boundary: clicking them or moving
focus into date/filter inputs must not flush an unsent form input or execute its
OnChange handler. The saved report excludes raw drafts. Native behavioural
measurements cover the underlying period reducer, not this browser pagination
or chooser extension.
