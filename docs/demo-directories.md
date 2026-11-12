# Historical kinds/directories compatibility and the current main demo

The historical `demo_directories_v1` source profile added the original **Склады**
catalog beside **ВидыНоменклатуры** in the local catalog application. You can
create, edit, save, close and reopen both catalogs in one SQLite database.
Each catalog has its own nine-digit decimal code counter.

Kinds still execute their admitted original form handlers. Warehouses have no
original form or object module; they use the existing, visibly labelled host
autoform. The ordinary autoform's Code input remains available, including its
existing explicit-code behavior. Leaving Code blank on a new record requests
automatic numbering. Warehouse names are not subject to the kind form's
three-character rule, and the host does not invent a warehouse handler.

This is a bounded local application, not native standard-form parity.
**In that historical partial profile, Номенклатура remains archived and unavailable for editing.** Its original
object validation, kind reference and warehouse rows are not silently skipped.
Warehouse records are a practical prerequisite for that later product flow,
not a claim that product references or tabular editing already work.

## Create and run

Use a fresh, disposable destination that does not already exist:

```console
python -m yadinassi --create-demo-db demo.sqlite --import-xml examples/demo
python -m yadinassi --ui --f demo.sqlite --open-browser
```

These commands use the one current `main-demo-v1` configuration. The partial
profiles described below remain compatibility behavior for existing databases,
not additional demo sources or recommended new databases. The exact historical
root XML survives only in a test-only fixture assembled with pinned original
catalog/form/handler bytes from `examples/demo`.

In the current main demo, select **Склады**. Create a record, enter its
Description, leave Code blank and Save. Close the card and database, restart
the application with the same file and reopen the saved record. Select
**ВидыНоменклатуры** to use the existing original-handler editor.

No Node, network connection or rewritten demo sources are needed at runtime.

## Storage and recovery boundary

- The profile reuses the v6 physical SQLite layout but has a distinct persisted
  source-profile marker. Older v6 kinds-only databases keep their original
  single-catalog admission. Inert v5 archives remain permanently inactive.
  There is no implicit upgrade or in-place migration.
- All 19 original files, including inactive product sources, are retained and
  checked byte-for-byte. The new profile first passes the complete existing
  kinds admission, then admits the module-free original warehouse metadata.
- Ordinary import cannot activate or downgrade the partial profile. Source
  profile, schema inventory and complete archive must agree on create and open.
  Swapping a marker does not activate another catalog.
- Only the kinds catalog appears in the original-form capability inventory.
  Warehouse autoforms do not obtain permission to execute archived BSL.
- Every transaction retains the existing source validation under the writer
  lock. Source drift blocks new warehouse writes too, even when only an inactive
  product module changed. Unsaved editor values remain visible after refusal.
- Existing opaque revisions, numbering, receipts and uncertain-commit recovery
  are reused. Historical receipt resolution does not authorize new writes after
  source drift. A committed-but-unrefreshed record is refreshed without another
  write. These are local host guarantees, not native 1C behavior measurements.

## Verification

`tests/test_demo_directories.py` covers both catalogs, untouched archive bytes,
profile isolation, admission refusal, independent numbering, original kind
handlers, warehouse create/edit/reopen, dirty close/discard, repeated Save,
source/generation drift, uncertain commit, pending refresh and read-only access.
Existing kinds, inert-source, importer, SQLite, controller and protocol tests
remain regression gates. No native integration scenario or browser acquisition
is changed by this slice. Host tests alone do not establish browser acceptance.

For the separate fresh profile that also enables the original product card's
bounded local form projection and mandatory object checks, see
[original demo products](demo-products.md). Existing directories databases retain
their two-catalog contract.
