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
of `Movements`, `Balance`, `Turnovers`. No SQL, BSL, arbitrary expression,
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
