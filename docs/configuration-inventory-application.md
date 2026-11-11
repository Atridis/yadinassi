# Source-bound inventory forms application

`accumulation-reference-forms-v1` is a separate opt-in source grant for fresh
physical format 15. It is not the existing `accumulation-reference-v1` core grant
and does not widen the scalar format-14 importer, default importer or existing
format-13 posting application. Schema and receipt encoding are unchanged.
Database/host integration must select the new exact marker explicitly; this
source module alone does not create or open a database or grant execution.

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
uses metadata identities, not these demo names. Source/profile checks are not
native UI parity evidence and do not claim the report/host adapter is complete.
