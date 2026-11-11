# One configuration-owned business application

`examples/configuration-business-application` is an authored configuration for
`configuration_business_v1`: Products and Categories catalogs, a non-posting
Orders document with scalar Lines, two common forms, client/server common
modules and one managed application module. No per-example Python host package
or native Designer/FormWrite parity is claimed.

## Create once, then open

From the repository root, explicitly create a **new** database:

```sh
python - <<'PYTHON'
from pathlib import Path
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
root = Path('examples/configuration-business-application')
files = {p.relative_to(root).as_posix(): p.read_bytes()
         for p in root.rglob('*') if p.is_file()}
backend = SQLiteCatalogBackend.create_business_application('business.sqlite', files)
backend.close()
PYTHON
python -m yadinassi.ui.configuration_app examples/configuration-business-application --business-application --f business.sqlite
```

The business flag opens an existing, explicitly granted fresh-v7 database. It
is not a migration or conversion command. Keep its complete configuration source
unchanged; canonical source/schema validation rejects a replaced form or module.
Use a different new database for a different example/source version. Historical
catalog, document-only and application grants are not implicitly expanded.

## Walk through the example

1. Startup calls server `Service.Add(7)`, which emits its server-process message
   and returns 8. Client `Tools.ShowWelcome()` opens the Business workspace.
   **Open details** makes another real server call and passes a scalar Message
   parameter to the Details form through the client common module.
2. **New product**, **New category** and **New order** call client `Tools`
   procedures that use `OpenForm` with declared metadata form names. The same
   objects are available through the application's catalog/document lists.
   Navigation does not copy a form's Object or context into the common module.
3. Give a product its explicit unique Code, Description and Price. Its checked
   form preparation trims the description and rejects blank descriptions or
   negative prices. The custom discount command changes Price by 10 percent.
   Save persists the object; the selected authoritative list refreshes without
   rewriting a dirty sibling card. Categories have their own scalar layout.
4. Create an order, enter Note, add lines and edit Label, Quantity and Checked.
   Select a row before **Delete selected line**. **Write document** persists the
   complete header and rows together. Reopen through the document list to see
   the durable image. Numbering is automatic; this example does not calculate
   totals or connect a line to a product.
5. Editing a card marks it dirty. Ordinary **Close form** runs its BeforeClose
   handler and refuses unsaved changes, rather than silently saving/discarding.
   Save and then close each card before ordinary application shutdown.

For a visible catalog validation refusal, use Description `Form reject` or
`Object reject`: the first is rejected by checked form preparation, the second
by the separately validated catalog ObjectModule. Correct the description and
save again. Document ObjectModule events are not admitted at all.

## Deliberate limits

- At least one document is required by this new profile; catalogs are optional.
  This example combines them, but neither product/category nor order-line
  relationships are reference fields. Text labels are text, not disguised Refs.
- Catalogs are scalar and non-hierarchical. Documents have scalar headers and
  scalar sections only. Posting is explicitly Deny; no Post/Unpost, movements,
  registers, document ObjectModule or unknown activation is enabled.
- Existing table bounds apply: four tables, eight columns per table, 32 rows per
  section, 256 cells and 32768 encoded table-data bytes. Overflow rejects rather
  than truncates. Dates persist and can be changed by BSL; the current date
  renderer is read-only, not a date picker.
- `WriteObject()` is the checked host service, not a claim of native standard
  FormWrite. Recovery retains uncertain write intent and post-commit refresh
  state; do not interpret a transport failure as permission to replay a write.
- Client/server common modules use the owned application runtime and explicit
  server-call transport. Independent form children do not acquire root
  transaction authority. Browser attachment ownership is not business-record
  concurrency or multi-user isolation.
