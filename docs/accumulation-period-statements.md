# Stock statements for an interval

The core query surface supports `BalanceAndTurnovers` / `ОстаткиИОбороты` over
existing Balance accumulation registers. Two required named Date parameters
select the interval. An optional literal `Day` / `День` or `Month` / `Месяц`
adds a `Period` / `Период` column. The same two periodicities are available on
`Turnovers` / `Обороты`. There is no Auto, Recorder, condition argument, omitted
boundary or completion-mode argument in this closed subset.

```bsl
Q = New Query("SELECT S.Product,S.Warehouse,S.QuantityOpeningBalance,S.QuantityReceipt,S.QuantityExpense,S.QuantityTurnover,S.QuantityClosingBalance FROM AccumulationRegister.Stock.BalanceAndTurnovers(&StartAt,&EndAt) AS S");
Q.SetParameter("StartAt", Date(2024,1,1));
Q.SetParameter("EndAt", Date(2024,4,30,23,59,59));
Rows = Q.Execute().Select();
```

Every resource exposes OpeningBalance / НачальныйОстаток, Receipt / Приход,
Expense / Расход, Turnover / Оборот and ClosingBalance / КонечныйОстаток.
Dimensions retain their scalar or typed CatalogRef identity. Numeric result
qualifiers are 38 digits with the declared resource scale and signed values.
Raw attributes, record type, recorder and line numbers are not virtual columns.

## Observed period behavior

Opening balance uses movements **before** Start. Receipts and expenses include
both Start and End. Closing balance includes those flows. The reducer uses
exact scaled integer arithmetic, including negative resources and cancellation.
A carry-only group remains. Equal nonzero receipts and expenses remain even
with a zero closing balance; a group with all zero totals is omitted.

Calendar output is **sparse**, not a filled calendar. It contains movement
buckets and nonzero opening/closing boundary rows. Intermediate months or days
without movements are not invented. The first period label is clipped to Start
when Start lies inside a bucket. Subsequent labels use calendar starts. Ordinary
WHERE, JOIN, ORDER BY and aggregate expressions operate on these typed rows.
Periodic all-zero rows are omitted: an unrelated zero-only occurrence must not
poison other groups or a residual WHERE (native case 10 follows the zero write
in case 6). The older **nonperiodic** `Turnovers` all-zero refusal remains explicit;
that separate legacy admission boundary is not widened here.

## Date envelope and evidence

The new combined/periodic sources deliberately admit query endpoints only from
**1900-01-01 through 2099-12-31 23:59:59**, at exact second resolution. This is a
**host scope limit**, not a claimed 1C calendar cutoff. Dates outside it fail
before a read lease is opened. Existing nonperiodic Balance/Turnovers and stored
Date/write admission are unchanged. No lower/upper native calendar limit is
inferred from one rejected extreme date.

Native acquisition [43054182621](https://github.com/Atridis/yadinassi/actions/runs/43054182621)
ran fourteen groups on 1C 8.3.27.1508. Its immutable source-bound capture is in
`tests/fixtures/native_inventory_period`. Installation, UpdateDBCfg, material
redump, input/runtime hashes and process/container cleanup were verified. Groups
1–13 cover empty qualifiers, carry, endpoints, zero groups, numeric scales,
reference identity/rename, clipped days/months, gaps, repost/unpost and rollback.
Group 14 separately observes refusal of extreme Date9999 writing and of three
query-only variants, with an ordinary-date control write. The failed initial
acquisition [43052158206](https://github.com/Atridis/yadinassi/actions/runs/43052158206)
stopped at the extreme write before its queries; it is not a parity golden.

The runtime regression compares groups 1–13 and group 14's query refusals. It
**does not claim extreme writer parity**: the pre-existing host writer still
accepts that Date, while native refused it. The probe rolls back either writer
outcome before the query controls. The acquisition report truthfully keeps
`runtime_parity_accepted=false`; capturing native behavior is not a host replay.
Scalar collation, authority checks and host resource limits are separate from
the reference-dimensional observation packet, not newly measured native claims.

## One snapshot and unchanged storage grants

The whole source is reduced on the existing actual document-owner read view,
including queries inside a posting transaction. There is no separate opening,
flow or closing query and no second snapshot. All source rows and fields are
validated and charged even when outside the interval or absent from projection.
Generated boundary rows are charged before projection, WHERE and TOP. Wide
intervals do not allocate a dense calendar or increase existing budgets.
No operation computes an overflowing End + 1.

Physical formats 14/15, canonical source checks, reference integrity, retained
read-handle invalidation and original source grants are unchanged. No schema
migration, index DDL, new write authority, forms or UI report manifest is added.
The existing UI report grant stays closed independently of this core query API.

## Fresh CLI example

Use a **separate fresh file**, not the older demo.sqlite or an existing grant:

```console
python -m yadinassi --create-db period-stock.sqlite --import-xml examples/inventory_reference/source --source-profile accumulation-reference-v1
python -m yadinassi --f period-stock.sqlite examples/inventory_reference/period_seed.bsl
python -m yadinassi --f period-stock.sqlite examples/inventory_reference/period_statement.bsl
python -m yadinassi --f period-stock.sqlite examples/inventory_reference/period_reconcile.bsl
python -m yadinassi --f period-stock.sqlite examples/inventory_reference/period_statement.bsl
```

The seed creates opening-only stock, normal receipts/issues and a product whose
receipts and expenses balance. The read-only monthly statement shows opening,
receipt, expense, net and closing quantities, including sparse boundary rows.
The separate reconciliation command reposts January's issue as 4 and unposts
March's issue. Reopening the statement then shows closing stock 11. The report
itself never posts, unposts or edits records. The original example's authored
negative-stock policy and its documented limitations remain unchanged.
