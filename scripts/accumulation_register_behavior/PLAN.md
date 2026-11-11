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

## Native source-derived declaration

`AccumulationRegister.xml` is a modified MPL-2.0 derivative of complete native
XML from vanessa-opensource/add, pinned at commit
`2deeed6636dfbb84f42ae625fd40c8ab662bb64e`. The complete unmodified inputs,
license, attribution and exact substitutions are in `public_source/vanessa_add`.
`native_source.py` deterministically reproduces the owned declaration offline;
it is not staged or imported by the native acquisition route or runtime importer.

The complete native namespace header, all five StandardAttribute descriptors,
and full Resource/Dimension wrappers come from `РегистрНакопленияОстатки.xml`.
The full Attribute wrapper alone comes from `РегистрНакопления2.xml`; its boolean
Type is replaced wholesale with the owned Note String type. No sibling catalog
references, modules, forms or permissions are imported. Resource*, Attribute*,
Dimension* order, original owned UUIDs and all six generated TypeId/ValueId
pairs are retained. Register type, locking, totals splitting, field groups,
scalar qualifiers and UseInTotals preserve the original sixteen-case design.
The document, handler, observer, grants and material redump gate are unchanged.

The input retains its truthful native schema **2.4**. Designer 8.3.27.1508 loaded
the full unmodified balance declaration and redumped it as 2.20 in diagnostic
run [42978092661](https://github.com/Atridis/yadinassi/actions/runs/42978092661),
source tree `9c190f8255be8c81372e493e010f472ec122cab1`. That diagnostic's strict
full-signature comparison did not pass, so it is not accepted native evidence
or parity and proves no specific cause of the earlier sparse-XML loader crash.
It supports using complete native wrappers rather than guessing another sparse
hybrid. The derived five-field declaration still requires its own successful
load, material redump verification and all sixteen observations.

Designer-added UI defaults and 2.4-to-2.20 serialization are not semantic
observations. The existing projection still checks the material fields,
qualifiers, identities, controls, document linkage and handler bytes. No gate is
weakened and no arbitrary native XML is newly accepted by runtime source grants.
In particular, this acquisition-only 2.4 input does not activate runtime import
support, aggregate rules, information-register uniqueness or any parity claim.
