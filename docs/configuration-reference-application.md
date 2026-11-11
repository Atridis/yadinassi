# Typed references in a configuration application

Development checkpoint, not a completed acceptance claim. This separate source
profile adds single-target CatalogRef fields to catalogs, document headers and
scalar document sections in the owned application host. Historical scalar
profiles do not acquire reference admission or profile-conversion authority.

The authored example extends the mixed application with Products.Category,
Orders.Category and Orders.Lines.Product. Server form state retains real typed
catalog references. A client replica receives an issued form-scoped identity,
presentation and empty marker, never a record UUID or server reader. This is a
private form transport, not native managed-form or generic invocation parity.

Choice uses existing non-deleted records, bounded exact-code filtering, explicit
overflow and one-shot owned tickets. Cancel preserves the previous value; Clear
assigns the typed empty reference. A removed row or replaced form cannot receive
a late result. Pending writes/refresh recovery do not permit a new selection.
Unknown outcomes lock rather than replay writes or pretend to cancel an action.

The profile creates a new v7 database explicitly with
`SQLiteCatalogBackend.create_reference_application(path, files)` and launches
with `--reference-application --f existing.sqlite`. Existing source bytes and
schema stay pinned at creation, reopen, transactions and export. No automatic
migration, DocumentRef, composite types, creation inside the picker, hierarchy,
posting/movements or new transaction authority is enabled. Client UUID/GetObject
and arbitrary reference assignment remain explicitly unavailable.

## Create once, then open

From the repository root, create a **new** database, not a conversion of an
existing scalar application:

```sh
python - <<'PYTHON'
from pathlib import Path
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
root = Path('examples/configuration-reference-application')
files = {p.relative_to(root).as_posix(): p.read_bytes()
         for p in root.rglob('*') if p.is_file()}
backend = SQLiteCatalogBackend.create_reference_application('references.sqlite', files)
backend.close()
PYTHON
python -m yadinassi.ui.configuration_app examples/configuration-reference-application --reference-application --f references.sqlite
```

Create and save a category with a Code and Description first. On a product card,
**Choose Category** opens the existing-record picker. Use **Exact code** when
more than 32 categories match; overflow is reported rather than truncated. Save
the product, then create an order, choose its Category, add a line and choose a
Product in that line. **Write document** saves the typed header and complete
rows. Reopen it from the declared document list to see persisted references.

**Cancel selection** preserves the existing value. **Clear** assigns the empty
reference of the declared target type, not an empty string. Both Apply and Clear
invoke the declared OnChange once only when the value changes; for table cells,
CurrentData identifies the changed row. No create-new command is hidden inside
the picker. Save/close a separate category or product card before selecting it.

Keep all source files unchanged after database creation. Reload can reconcile an
already submitted draft and owned picker, but cannot promise to preserve raw
inputs not yet sent to the host. A lost mutation reply locks the application
rather than replaying it. This feature does not alter browser attachment
ownership, uncertain-write recovery, or independent child transaction denial.

## Validation status

The first frontend run passed 293 JS checks. The first 39 Python cases had
one test-fixture control-name mismatch, now corrected; the combined regression
and four real Chromium acceptance flows are still pending. This is not a full
validation or native reference-form parity claim.
Client references support identity equality, presentation and IsEmpty only;
client TypeOf/TypeDescription and reference-object access are not claimed.
