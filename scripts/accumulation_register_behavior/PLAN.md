# Owned accumulation-register observations

Status: authored acquisition source, not recorded native evidence or runtime
parity. Exactly sixteen numbered observations execute in one fresh isolated
NativeSmoke infobase after official XML import and material redump verification.
No existing native fixture, production database or posting profile is modified.

The owned fixture has one document, one Balance-kind accumulation register,
Item/String and Warehouse/Number dimensions, Amount/Number(10,2) and
Quantity/Number(10,3) resources, and Note/String attribute. Both dimensions have
UseInTotals=true. Direction uses native AccumulationRecordType, never a surrogate.

1. Empty Balance/Turnovers results; scalar Unload Number qualifiers for both
   balance resources and Amount turnover/receipt/expense outputs.
2. Identical dimensions and period twice within one recorder; default Active,
   RecordType, Period and LineNumber inspected before explicit assignments.
3. Same dimensions and period in a second recorder, compared with case 2.
4. Positive and negative resources with both Receipt and Expense directions.
5. Active and inactive movements; raw persisted rows versus virtual totals.
6. Balance before, exactly at and after three adjacent movement timestamps.
7. Turnovers start/end inclusion and an equal-endpoint interval.
8. All-resource zero cancellation versus Amount=0 with nonzero Quantity.
9. Multiple dimensions, differing attributes, decimal precision and a sum that
   exceeds the precision of a single stored Amount.
10. Case-distinct String dimensions and grouping identity.
11. Two explicit recorder replacements and query visibility inside the handler.
12. Repost the same object after adding a row, then repost a freshly loaded object
    with no supplied rows. No buffer-load behavior is assumed beforehand.
13. Ordinary Write preservation followed by UndoPosting and readback.
14. Cancel after explicit movement writing, followed by independent readback.
15. Raise after explicit movement writing, followed by independent readback.
16. Outer transaction rollback, followed by readback in a subsequent transaction.

Each numbered result may contain several bounded scalar subobservations. Failed
writes are recorded with diagnostics and successful independent readback, not
silently changed to expected success. A setup/query/readback failure leaves the
case incomplete and cannot become accepted evidence. All sixteen results,
entered/completed witnesses, nonce, source/configuration hashes and verified
process/container cleanup are required. No output becomes a golden automatically.

The new route adapts the existing isolated posting lifecycle, pinned image,
nonroot/no-network/read-only-root constraints, bounded outputs and credential
cleanup without changing the original route. Before running tests or creating
a PR that triggers native acquisition, the coordinator must announce exact local
counts and the sixteen-case native count. A source branch push alone is an early
checkpoint, not test execution or evidence.

Public XML structure was inspected read-only at:
https://github.com/vanessa-opensource/add/blob/2deeed6636dfbb84f42ae625fd40c8ab662bb64e/lib/CF/83xdd/AccumulationRegisters/РегистрНакопленияОстатки.xml
Only schema structure informed this candidate. Fixture UUIDs, field names,
modules and data are newly authored. Designer acceptance remains required.
