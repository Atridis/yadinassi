# Explicit document object forms

`configuration_documents_v1` is a separate, document-only source grant. The
host imports the whole source with `import_document_forms_configuration`, then
loads forms with `load_configuration_forms(files, document_schemas=config.documents)`.
The canonical projection admits only declared managed forms with one main
`Object` of the matching `cfg:DocumentObject.<name>` type. Posting must be Deny.
ObjectModule files, object events, references, catalogs, CommonModules and
application modules are rejected, not silently ignored. Composition needs a
separate reviewed profile; existing catalog/application grants are unchanged.

Scalar paths `Object.Number`, `Object.Date`, `Object.DeletionMark` and declared
header fields become typed form buffers. A `Table` item binds to a declared
`Object.<section>` with fixed scalar columns. BSL uses the ordinary form table
collection through the checked AST projection, for example
`Row = Object.Lines.Add(); Row.Flag = True;`. There is no second evaluator and no
live DocumentObject on the wire. Arbitrary Object paths and NoContext access
remain rejected. Form BeforeWriteAtServer is not admitted in this first profile.

`FormDefinition.create_server(object_session=DocumentObjectSession(...))`
checks the exact source/schema before construction and loads all fields/rows
before OnCreate. `WriteObject()` is an explicit context-server host service,
not a native standard FormWrite claim. It sends one complete DocumentImage to
the coordinator. The coordinator persists through ordinary DocumentObject.Write,
without posting modes, and retains uncertain intent/committed refresh state.
Recovery ignores subsequent buffer edits and never repeats a committed write.
The host may supply `projection_preflight(listing)` on the coordinator for its
closed list envelope before reporting save success.

Row UUIDs live only in the server session's mapping; form integer IDs are opaque.
The existing UI budgets remain: four tables, eight columns per table, 32 rows
per table, 256 total cells and 32768 encoded table-data bytes. Overflow rejects
open/save without truncation. The persistence coordinator's 1000-row ceiling
is not a promise that the UI can display 1000 rows. Complete packet validation
precedes successful authoritative projection. Dirty sibling sessions are not
updated by this adapter. Date values persist and are editable by BSL; the
existing renderer's date field is read-only, not a date-picker promise.

## Shipped authored example

`examples/configuration-document-forms` declares a non-posting Orders document,
Note header, and Label/Quantity/Checked rows. Add line and Delete selected line
are BSL commands over the actual table collection. Write document writes the
whole image; it neither posts nor calculates totals. The renderer's ordinary
**Close form** command runs BeforeClose and refuses unsaved changes. There is
no invented BSL Close method or implicit Save/Discard.

The opt-in launcher is:

```sh
python -m yadinassi.ui.configuration_app examples/configuration-document-forms --document-objects --f PATH_TO_FRESH_DATABASE
```

Create the
fresh database explicitly with `SQLiteCatalogBackend.create_document_forms(path,
files)`, where `files` is the relative-name to bytes mapping of the example.
For example, from the repository root, create a new database once:

```sh
python - <<'PYTHON'
from pathlib import Path
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
root = Path('examples/configuration-document-forms')
files = {p.relative_to(root).as_posix(): p.read_bytes()
         for p in root.rglob('*') if p.is_file()}
SQLiteCatalogBackend.create_document_forms('orders.sqlite', files).close()
PYTHON
python -m yadinassi.ui.configuration_app examples/configuration-document-forms --document-objects --f orders.sqlite --open-browser
```

Creation must fail if the destination already exists. Do not use this source
with `--application-host` or a catalog source grant. This document-only example
has no ObjectModule, posting mode, CommonModule or external service.

The fresh grant uses the existing non-posting v7 storage layout. Explicit v11
migration refuses this source profile before opening its writer. Reopen, every
transaction and configuration export revalidate the exact source and persisted
schemas; a source or schema change is not an implicit configuration upgrade.

The document list uses opaque per-launch record keys, not database/record UUIDs.
Commands sit above the list and operate on the current selection. Open selected
requires exactly one selected row; selecting several never silently performs a
batch. A successful write refreshes the authoritative list immediately while
retaining independent sibling drafts. The host shows a refusal rather than
truncating a list beyond 256 records.

The launcher uses the single-writer browser attachment model. A second browser
tab is an observer until an explicit takeover. Closing a browser tab is not a
save, discard, or rollback command; open/dirty/uncertain forms retain the owned
process for safe recovery. Use Close form, then Close application for an explicit
clean exit. See the [application lifetime rules](configuration-application-host.md)
for the advisory-detach and real lease-expiry boundaries.
