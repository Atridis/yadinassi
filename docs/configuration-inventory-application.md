# Source-bound inventory forms application

`accumulation-reference-forms-v1` is a separate opt-in source grant for fresh
physical format 15. It is not the existing `accumulation-reference-v1` core grant
and does not widen the scalar format-14 importer, default importer or existing
format-13 posting application. Schema and receipt encoding are unchanged.
Database/host integration selects the new exact marker explicitly. The source
module alone does not create or open a database or grant execution.

The source contains flat scalar catalogs, reference-bearing posting documents,
Balance accumulation registers, their original object handlers, and explicitly
declared managed object forms. Every catalog/document has a declared default
object form. CommonForms, CommonModules, enums, extra executable files and
undeclared metadata are refused. The form loader's existing typed field,
reference-target, section and lifecycle checks remain in force.

## Full source and trusted projection

`import_inventory_application(files, inventory_runtime=PROFILE)` returns an
immutable `InventoryApplicationConfiguration`. `files` retains all original
bytes, including form modules and the manifest. `source_digest` binds that full
inventory; `core_projection_digest` identifies only a temporary core-validation
projection. Metadata IDs, generated native type/value IDs, handler hashes,
reference targets and recorder ownership must remain exact.

`canonical(configuration)` reimports the complete source and compares the exact
typed result. `validated_core(configuration)` performs the same full check before
returning the core projection. That projection is not original source and must
not replace the saved source or admit a new application under an old marker.
Projection removes only validated form/default-form metadata and preserves
QName namespace bindings without changing the global XML namespace registry.

## Closed manifest

`InventoryApplication.xml` is an authored host extension, not native standard
command metadata:

```xml
<InventoryApplication xmlns="urn:yadinassi:inventory-application:1" version="1">
  <Forms>
    <CatalogForm name="Catalog.Products.Form.Card"/>
    <DocumentForm name="Document.Receipt.Form.Card">
      <Command name="Write" id="3" mode="Write"/>
      <Command name="Post" id="4" mode="Post"/>
      <Command name="UndoPosting" id="5" mode="UndoPosting"/>
    </DocumentForm>
  </Forms>
  <Reports>
    <Report name="StockBalance" register="Stock"
      registerId="9ea1e3ef-4d1e-5933-b5ff-923cb2084491" view="Balance"/>
  </Reports>
</InventoryApplication>
```

All declared forms need exact manifest bindings. Catalog entries grant no posting
host commands; their existing owned `WriteObject()` lifecycle remains ordinary.
Only document forms get the authoritative read-only Posted projection and host
synchronization hook. Each document has exactly one command for each of Write,
Post and UndoPosting, bound to its declared name, numeric ID and an empty,
synchronous, one-argument client handler. A button's name alone grants nothing.
The host effect belongs after successful form dispatch, not inside that BSL
handler; this is not synchronous native FormWrite parity.

Reports are immutable read-only grants. Names are bounded identifiers; register
name and UUID must match the admitted register exactly. The only views are
Movements, Balance and Turnovers, with no duplicate register/view pair. The
manifest carries no SQL, BSL, filter expression or browser-chosen persistent
identity. Concrete report services must enforce their own bounded typed inputs,
source/database binding and opaque wire capabilities.

Unknown fields, namespaces, versions, duplicates and extra bodies are rejected.
No callbacks, root authority, migrations, CommonModules or report writes are
implicitly enabled.

## Authored example

`examples/configuration-inventory-application` extends the verified authored
`inventory_reference/source` with Products/Warehouses cards, Receipt/Issue
reference-bearing document cards and three Stock reports. Its core schemas and
posting handler bytes are unchanged. The Issue handler's negative-stock check
is an authored business rule, not a built-in platform policy. Runtime admission
uses metadata identities, not these demo names. Source/profile checks are not native UI parity evidence. Browser acceptance is
a separate required step; a passing controller test is not a Chromium result.

## Create and open the explicit demonstration

Create a **new** database with the reviewed source grant, never convert an old
core15/demo database or replace its marker:

```python
from yadinassi.configuration_import import read_configuration_directory
from yadinassi.configuration_inventory_application import import_inventory_application, PROFILE
from yadinassi.sqlite_catalog import SQLiteCatalogBackend

files = read_configuration_directory("examples/configuration-inventory-application")
configuration = import_inventory_application(files, inventory_runtime=PROFILE)
SQLiteCatalogBackend.create_inventory_application("db/inventory.sqlite", configuration).close()
```

The destination must not exist and its parent directory must already exist. Then:

```console
yadinassi --ui --f db/inventory.sqlite --open-browser
```

The launcher reads the exact stored source; no external directory or extra
profile argument is needed on reopening. Raw core15 and format14 remain refused.
The explicit source-development route is `--configuration-ui DIRECTORY
--inventory-application --f DB`, with the same full-source checks.

Create Products and Warehouses cards, then a Receipt with an explicit number,
warehouse and product lines. Write saves without posting; Post changes document,
Posted and movements in one root operation. Undo posting clears its movements.
An Issue that exceeds available stock is refused by the example's authored
handler. Catalog save refreshes the selected list without replacing sibling drafts.

Object forms currently admit at most 32 rows per table. Storage and read-only
report limits are separate: a valid saved document can exceed this form bound.
Opening such a document is refused without truncating its lines; the current
creation-failure path locks the UI connection. Copy unsaved sibling edits before
closing that host and reopening the base. A nonterminal, preflight capacity
message is a follow-up UX task, not
implemented by the statement paging extension.

Document close compares the complete authoritative typed image and pending
receipt, not the example's local Dirty flag. An uncertain or committed-but-not-
refreshed operation stays locked and uses its original receipt; the UI never
replays handlers or claims rollback. Receipts are retained for this host lifetime,
not durable recovery after process loss.

Stock reports are read-only saved-state projections. Balance is strictly before
the selected instant; Turnovers includes both endpoints. Labels and typed values
come from one snapshot. Unsaved form inputs are not included, report reading
does not resolve an operation, and pending receipts block reports. Changing form
state clears an old projection; changing period controls never relabels the old
result. Large results are refused as a whole, not silently truncated.

## Explicit period statement grant

The example additionally declares `StockStatement` (`BalanceAndTurnovers`) with
source-bound `None`, `Day`, `Month` periodicities and exact Product/Warehouse
catalog-dimension filter identities. The original three report declarations
remain unchanged and remain valid without this extension. Only the new report
accepts these closed children; no profile, database format, posting command or
BSL authority is widened. See [the report contract](inventory-application-reports.md#source-declared-stock-statements)
for typed filters, same-lease admission, date bounds, sparse rows and detached
read-only results.
