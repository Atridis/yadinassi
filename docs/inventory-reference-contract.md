# Inventory with typed catalog identities

Native reference observations were acquired on **1C 8.3.27.1508** in
[run 43030189023](https://github.com/Atridis/yadinassi/actions/runs/43030189023).
The scalar accumulation 16-observation baseline is separate evidence.

The explicit `accumulation-reference-v1` grant is fresh-only format **15**. It
composes scalar, flat catalogs, posting documents (including typed header and
line CatalogRef fields), and Balance registers with typed CatalogRef dimensions
or attributes. Resources stay numeric. Catalog fields stay scalar. No forms,
CommonModules, independent managers, composite references, DocumentRef fields,
IR/accumulation combined configuration or migration is granted.

This is a distinct storage contract: catalog data/layout tables and numbering
sequences are populated; movement schemas have a new exact value-domain tag and
persist their target catalog UUIDs. Version 14 remains scalar-only, with its
original schema bytes and receipt hash domain. Changing only a version or marker
must never admit the other profile. Creation/open retain and reimport exact
source bytes, compare all projected schemas, and never execute source handlers.

A stored reference binds database, metadata target and record UUID, never Code
or Description. Nonempty targets must exist in the same borrowed transaction.
Empty references are typed, distinct from NULL/Undefined. The measured public
assignment conversion is narrow: an owned CatalogRef in the current metadata
family but of the wrong catalog becomes the target catalog's typed empty value.
Native group 2 measured this separately for the document header, document line
and document-owned movement dimension. Foreign database/family references,
unowned or forged references and non-CatalogRef values are refused, not coerced.
These authority checks, referential integrity and resource budgets are host
safety rules, not native parity. Storage validation never repairs wrong targets.
Movement JSON cannot rely on SQLite foreign keys for this check. Source guards,
coarse budgets, scalar validation and full reference validation are distinct.

One existing unit of work owns catalog/document writes, Posted, replacement
movements and durable receipts. A catalog created earlier in that transaction
can be referenced by its document. Savepoint cancellation rolls back all of the
posting operation; outer rollback also removes prior staged catalog creation.
Uncertain recovery resolves receipts and does not rerun document handlers.

Native gate: install the separately owned fixture, validate material redump,
then acquire 12 source-bound observation groups for typed defaults/assignments,
persistence, two-recorder receipts/issues, reference grouping/JOIN/equality,
identity despite equal or renamed descriptions, repost/ordinary write/unpost,
explicit movement write/query rollback and enclosing transaction rollback. The
old scalar observer remains unchanged. The immutable observation and original
provenance are in `tests/fixtures/native_inventory_reference/`. Acquisition
accepted the installed material redump, all 12 numbered observations and both
process/container cleanup witnesses. Original capture binding: head
`4bef30e9a9a166067344fa3ccbf45073cc952892`, admitted merge
`b52465db5dd71407eceb2f3af85f6f5e84263d6f`, tree
`5dbb273f6e7bf8b61bdf5d2e83ac4833d1c30fbf`, 228 interpreter files.
The original acquisition report truthfully retains `runtime_parity_accepted=false`: it
only measured native behavior. The regression suite separately replays all 12
groups against the authored runtime source, including the measured conversion;
it does not rewrite the acquisition report or claim a complete 1C implementation.

## Runnable stock example

The owned example uses public BSL and separate CLI invocations; it does not need
browser forms. Run once against a fresh file:

```console
python -m yadinassi --check-xml examples/inventory_reference/source --source-profile accumulation-reference-v1 --report-json
python -m yadinassi --create-db inventory.sqlite --import-xml examples/inventory_reference/source --source-profile accumulation-reference-v1
python -m yadinassi --f inventory.sqlite examples/inventory_reference/run.bsl
python -m yadinassi --f inventory.sqlite examples/inventory_reference/reopen.bsl
```

The scenario posts a receipt of 10 and an issue of 3, refuses a second issue of
100, unposts the first issue, then reposts it with quantity 2. The final reopened
balance is 8; the reopened Turnovers report shows receipt 10, expense 2, net 8.
The negative-stock rule lives in the example's Issue handler,
which explicitly writes its movements and queries the same transaction. This
is not a universal 1C rule, cost accounting, or prevention of every possible
backdated oversell: the example checks the balance one second after its own
Date. Production applications must author the business policy they require.
