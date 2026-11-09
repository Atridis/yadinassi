# Replicated order form with fixed-schema lines

This host-functional example composes the form model, isolated client/server BSL,
local browser renderer and existing SQLite catalog tabular storage. It does not
claim native 1C managed-form parity. The XML is an authored configuration in the
supported official-format subset, not a native acquisition or Designer export.

For editing already saved orders, use the [existing order workbench](order-workbench.md).
It adds retained object/revision sessions, continued editing after save and explicit discard.

## Run the complete workflow

From a checkout with the project dependencies installed:

```sh
python -m yadinassi --create-db orders.sqlite --import-xml examples/forms/order-intake/configuration
python -m yadinassi.ui.form_app examples/forms/order-intake --f orders.sqlite --open-browser
```

Database creation is explicit. The launcher only opens an existing database.

1. Enter an order code (1–8 characters) and description (1–64 characters).
2. Select **Add line**. The server creates and selects a new line with Quantity 1.
3. Enter Description, Quantity and Price. Add further lines as needed. Amount and
   Total are read-only and are deliberately not recalculated on each keystroke.
4. Select a row, then **Delete selected line** to remove it. Selection belongs to
   the table control; it is not a row index or a database identifier.
5. Select **Recalculate** to compute line amounts and the header total on the
   server. Recalculation does not save or clear the unsaved-changes flag.
6. Select **Save order**. The server validates all inputs, checks the code, derives
   amounts and total again, builds one new CatalogObject and writes its header
   and every line in one existing `CatalogObject.Write` operation.
7. After success, editing and all commands remain locked. Close the clean form.
   Restart the launcher for another new order.

Each line needs a nonblank description of at most 128 characters. Quantity must
be positive, Price nonnegative, both at most 1,000,000 and both with at most two
fractional digits. Each Amount is `Round(Quantity * Price, 2)`; Total is the sum
of those rounded amounts. For example, quantities/prices 1.25/2.35 and 2/3.10
produce 2.94 and 6.20, totaling exactly 9.14. Decimal text never passes through
binary floating point. The app validates rather than silently rounding input
quantities or prices to fit storage. The user-facing `Lines.Description` maps
explicitly to stored `Catalog.Orders.Lines.ItemDescription` in SaveOrder. The
existing storage schema reserves Description, so no storage rule is widened. Its fixed bounds keep all amounts/totals
within the configuration's Number(18,2) storage fields.

The browser flushes and validates all pending cell/field edits before commands,
row selection or close. Invalid drafts are not silently dropped. OnChange
marks Dirty locally; a prebound command crosses the byte transport and delivers
pending scalar/cell edits and selection before server code runs. Add/Delete
operate only on the server. Deleted row IDs are never reused in that session.

## Save failures and close

Recoverable input errors occur before the save-attempt lock. The form retains
its values, displays a specific status, and remains editable so the user can fix
inputs and try Save again. Recalculate also validates before changing totals.
A duplicate-code precheck helps ordinary mistakes; it is not a concurrency lock.

Immediately before `Write`, the server sets SaveAttempted and locks the editable
fields, table and every command. The lock is deliberately conservative:

- Success sets Saved, clears Dirty and displays “Order saved”.
- A known server error can occur after a real database commit. The returned state
  therefore keeps the save-attempt lock, even when the transport is certain.
- A lost or malformed server response makes the whole session uncertain. No
  further event is sent and no automatic retry or new record is created.

Do not infer rollback from either error. Before creating another form/session,
independently inspect the database for the order code and verify the full header
and lines. A matching code alone is insufficient to establish the intended save.
If a record exists, reconcile it instead of creating a duplicate; if absent,
decide explicitly whether to start a fresh intake. There is no retry button,
receipt-recovery workflow or automatic reconciliation in this example. The
CatalogObject is local to the one SaveOrder handler: server module `Var` values
do not persist between contextful activations, so keeping an object in a module
variable would not make retries safe.

Normal Close cancels while Dirty is true, including after a failed save attempt.
The message explains the remaining work. Stop the launcher to abandon a locked
form, but reconcile any attempted write before restarting. Host teardown discards
unsaved client state; it does not undo database effects. Closing an untouched form
or a successfully saved form succeeds. Reattaching to the same launcher does not
reinitialize the form or resend Save.

## Trusted v1 package and fixed schema

`examples/forms/order-intake` has four fixed application files: client.bsl,
client.json, server.bsl and server.json. The sibling configuration directory is
an explicit database-creation input, not browser data. The v1 manifests declare
`yadinassi-form-app/1`; existing scalar-only v0 packages remain accepted.

The server manifest retains ordinary scalar `attributes` and adds `tables`:

```json
{
  "name": "Lines",
  "title": "Order lines",
  "columns": [
    {"name": "Description", "type": "String", "title": "Description", "readOnly": false},
    {"name": "Quantity", "type": "Number", "title": "Quantity", "readOnly": false},
    {"name": "Price", "type": "Number", "title": "Price", "readOnly": false},
    {"name": "Amount", "type": "Number", "title": "Amount", "readOnly": true}
  ]
}
```

This object is an entry in the `tables` list. Schema types are scalar String,
Number, Boolean or Date with default form TypeDescription qualifiers. Storage
qualifiers in the XML are separate and do not change the form schema. A trusted
Python host can use frozen `FormTableSchema`/`FormTableColumn` values with bounded
scalar type descriptions. A table is not a ValueTable attribute or a dynamic
nested FormAttribute. Scalars and tables share one case-insensitive namespace;
`GetAttributes()` intentionally enumerates scalar attributes only.

Server initialization adds `Items.Add("LinesTable", Type("FormTable"))`, binds
DataPath to `Lines`, and binds OnChange to the declared client Changed handler.
Columns derive only from the registered schema, not from renderer requests.
`ThisObject.Lines` exposes Count/Get, iteration and scalar cell access;
Add/Delete/Clear are server-only structural operations. The collection cannot be
replaced, constructed publicly, persisted directly or passed through scalar
Invocation arguments/results. Deleted, foreign and detached row handles reject.

`Items.LinesTable.CurrentData` is the selected owned row or Undefined.
`CurrentRow` is its positive Number ID or Undefined; trusted handlers may assign
a valid owned ID or Undefined. `row.GetID()` returns a Number. Cell edits select
the row before invoking the table's OnChange handler with the table control.
Selecting a row alone changes selection without a claimed native selection event.
Each registered schema permits one bound FormTable control. A second control
bound to the same DataPath rejects; at most four table controls exist per session.

## Boundaries and limits

The private replica protocol is `yadinassi-form/1`; the renderer protocol is
`yadinassi-form-ui/1`. UI cell events carry only control, row ID, column, exact
revision and a tagged scalar; selection carries an owned row ID or null. The
browser cannot choose database paths, table schemas, row structure, routines or
endpoints. A table's readOnly flag and each column's readOnly flag are enforced
by the host for cell edits, alongside visible/enabled state. View-only row
selection remains available on an enabled read-only table; it invokes no handler
and does not change cells. Busy, disabled and uncertain states block selection. Date, Null and Undefined values
remain display-only in the initial renderer. Private table state preserves exact
Date ticks, including default and fractional values; ordinary Invocation
arguments/results retain their narrower Date admission.

Explicit host budgets are 4 tables per session, 8 columns and 32 live rows per
table, 256 total live cells and 4096 monotonically allocated row identities per
table lifetime. The aggregate compact UTF-8 tagged cell data across all tables, including table
and row IDs, is bounded to 32,768 bytes before mutation. Table cell strings also
consume the form's existing 262,144-character aggregate scalar-text budget.
Schema/frame overhead is separate; the global frame cap remains 131,072 bytes. These are resource budgets, not native 1C maxima.
Scalar APIs and their existing budgets are unchanged. Replica installation
validates the complete response before mutation and preserves retained row
identities. No row handles cross processes.

The renderer keys controls/tables/rows/cells by stable identities. The table
item also carries a positive controlId (maximum 1024), which changes when a
control is removed and recreated, so drafts cannot migrate into a replacement.
It serializes requests and
never replays a failed write. Drafts for unaffected cells remain local; drafts for
removed rows or changed schema are discarded. Read-only, busy and uncertain
states prevent editing. Table commands are ordinary trusted BSL buttons, not
browser structural mutation capabilities.

## Verification and exclusions

`tests/test_form_table_app.py` covers schema/package admission, controller edits,
selection/delete, exact recomputation, recoverable errors, conservative save
locking, a fault after a real SQLite commit, and loss after a separate-process
save. Its end-to-end flow starts the real FormProcess, edits multiple lines,
deletes a selected line, saves, closes the child, independently reopens SQLite
and verifies the exact header, row order, quantities, prices and amounts.
The fourth scenario in `tests/browser_ui/form_browser_qa.mjs` adds actual
browser edits, immediate command flushing, identity-based selection/deletion,
invalid-draft refusal, a narrow screenshot, save locking and independent durable
readback. It runs only through the existing reviewed form-browser branch and
preserves the one sandboxed Chromium launch, loopback-only routing and fixed
resource/cleanup limits. Its screenshot is `order-table-narrow.png`; review the
actual image and source-bound report before claiming browser acceptance.

Core/replication tests and `frontend/form/test` cover their respective identity,
budget, packet and draft boundaries. Test results must be reported against the
actual candidate; this guide does not claim that tests or native acquisition ran.

This slice adds no native parity claim, reference control, existing-object
editing, nested/dynamic table schemas, sorting/filtering, new storage engine or
network deployment. Local process/HTTP/security behavior is described in
[the form application guide](form-app.md).
