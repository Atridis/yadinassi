# Edit existing orders in a replicated form

This opt-in example opens and edits an existing `Catalog.Orders` record, including
its complete `Lines` section. It uses the same authored Orders configuration and
business rules as [order intake](form-tables.md). It is a host-functional vertical
slice, not evidence of native 1C managed-form parity.

For continuous list → create/edit → retained form tabs without restarting Python,
use the [Orders workspace](orders-workspace.md). The standalone flow below remains supported.

## Run it

Use a database created with the existing intake configuration. To create a sample
order first:

```sh
python -m yadinassi --create-db orders.sqlite --import-xml examples/forms/order-intake/configuration
python -m yadinassi.ui.form_app examples/forms/order-intake --f orders.sqlite --open-browser
```

Create and save an order, close its form, and stop that launcher. Then run:

```sh
python -m yadinassi.ui.form_app examples/forms/order-editor --f orders.sqlite --open-browser
```

No database creation or migration happens when opening the editor. The server
opens the database; the browser and logical client receive only bounded scalar
form state. The four files in `examples/forms/order-editor` are trusted local
application inputs, never browser-selected source or paths.

## Complete workflow

1. The read-only **Existing orders** table shows at most 32 results. Leave
   **Find exact code** empty for the first 32, or enter an exact code and choose
   **Find orders**. A message explicitly says when more results exist. Search
   neither loads a partial editable object nor holds an open read transaction.
2. Select a result and choose **Open selected order**. The complete header and
   every line must fit the form budgets before anything replaces the active
   record. Missing/deletion-marked records or oversized records reject intact.
3. Edit code, description, line description, quantity and price. **Add line** and
   **Delete selected line** change the server-owned form collection.
   **Recalculate** validates and derives amounts without writing.
4. **Save changes** validates and recalculates once more, then writes the same
   selected object using its original revision. The editable code is data, never
   the save target. A successful save reloads the complete committed object,
   clears Dirty, and leaves the editor usable. An unchanged repeated Save does
   not start a database write.
5. **Discard / Reload** explicitly abandons pending browser drafts, including
   invalid decimal text, and reloads the selected record from the database.
   Other commands still validate and flush all pending inputs. Discard is the
   only explicitly bound draft-abandoning command; button names have no magic.
6. Save or discard before opening another result. Close cancels while the form is
   dirty or a save outcome is unresolved. Browser navigation also has an unload
   guard for local drafts, submitted unsaved edits and requests in progress.

Quantity must be positive; Price must be nonnegative. Both must be at most
1,000,000 with no more than two decimal places. Each line needs a nonblank
1–128-character description. Code and order description require 1–8 and
1–64 characters. Amount is `Round(Quantity * Price, 2)` and Total sums those
rounded amounts, with exact decimal arithmetic. User-facing `Lines.Description`
maps to stored `Lines.ItemDescription`; no storage naming rule changes.

The result table is a bounded snapshot; **Find orders** refreshes it after saves.

**Refresh state**, in the renderer header, reads the existing logical client
snapshot. It does not query the database, resolve a write or reconnect a lost
transport. Use the application commands described below for database recovery.

## Errors and recovery

- **Validation or known database rejection:** edits remain visible and editable.
  Correct the input and Save, or Discard / Reload.
- **Optimistic conflict:** another writer changed this record since it was opened.
  Save preserves the original expected revision and does not overwrite the other
  writer. Your draft stays visible. Copy anything you need before choosing
  Discard / Reload, which adopts the current database version. There is no merge UI.
- **Database commit outcome uncertain, healthy transport:** the server retains
  the same object and exact submitted intent. All editing, switching, discard
  and ordinary Save are locked. **Resolve save outcome** explicitly checks its
  receipt. A proven absent receipt may retry only that exact retained intent;
  a known receipt never duplicates the write. Transient resolution errors keep
  the lock. Resolution does not reinterpret newly edited data.
- **Commit confirmed, refresh failed:** **Refresh saved record** only reloads
  the selected object. It cannot write again. Failed whole-projection admission
  after a commit is also a refresh obligation, never permission for another Save.
- **Transport lost or response malformed:** the logical session is terminally
  uncertain. No command reconnects, retries or replays it. Inspect the durable
  database independently before deciding how to proceed. Do not infer rollback
  from a missing response. Stopping the launcher does not undo committed effects.

If ordinary Reload fails, the old server buffer and selected identity stay intact.
An explicitly requested Discard still abandons raw browser-only text when an
ordinary authoritative response arrives. The status explains the failure and the
retained server edits remain Dirty. A missing/malformed response instead keeps
raw drafts and locks the browser.

## Trusted host seam and package v2

`yadinassi-form-app/2` adds a closed server `application` selector,
`orders-workbench/1`, plus client `discardCommands` command/handler pairs and a
`dirtyAttribute`. Versions 0 and 1 remain accepted unchanged. Unknown application
selectors, undeclared discard handlers and malformed inventories reject at load.
The renderer receives only the derived button identities and Boolean dirty flag;
it cannot supply these declarations in an event. The controller checks the live
command/handler binding before exposing draft-discard semantics.

`FormServerBinding` is a small trusted-host inventory of zero-argument callbacks.
Names may not collide with form attributes, tables, module routines/variables,
existing functions or another binding. Callbacks receive the owning session and
may return only a form scalar. Fresh server activations invoke those same retained
callbacks; ordinary BSL module `Var` lifetime remains unchanged.

The closed `OrdersWorkbenchSession` retains the selected detached CatalogObject,
baseline, server-issued result-row-to-record mapping, form-line-to-storage-row
mapping and pending-save state. These objects, backend UUIDs, revisions and write
receipts never enter the replica protocol. Existing line identities survive
ordinary edits; newly added lines receive new storage identities. Each load,
discard or successful refresh allocates fresh monotonically increasing form row
IDs, so stale cell events cannot target another record.

Loading and refresh preflight the entire header/line projection using aggregate
form-table validation and the existing detached replica decoder, including a
complete response byte check, before installing anything or adopting the new
object/baseline. There is no `FindByCode`/`GetObject` inside Save before Write:
reloading there would silently adopt the latest revision and defeat conflict
protection. Known post-commit refresh is deliberately a separate operation.

The fixed mapping requires precisely the authored Orders header/section field
shape. This is not a generic object editor or arbitrary plugin loader. The
replica wire stays `yadinassi-form/1`; optional renderer metadata does not add a
new event kind or any object-valued transport capability.

## Bounds and verification

The two tables share the existing limits: 32 rows per table, 256 aggregate live
cells, 32 KiB of tagged table data, 131,072 bytes per frame and 4096 monotonically
allocated row IDs per table lifetime. The read-only result table has three
columns, leaving room for 32 complete four-column editable lines. Exhausted
row identities require a new session after any write outcome is reconciled.
No record is edited as a truncated subset.

`tests/test_order_workbench.py` exercises real SQLite and an owned server process:
load/edit/add/delete/recalculate/save/reopen, continued edits, unchanged Save,
identity preservation after code changes, two-writer conflicts, dirty close,
discard, stale IDs, complete oversized-load refusal, transient reads, uncertain
commit receipt resolution, post-commit refresh failures and terminal transport
loss. `frontend/form/test/discard.test.mjs` covers the explicit draft policy,
invalid decimals, unchanged legacy behavior, unavailable controls, pending-save
locks, dirty navigation protection and record-switch draft isolation.

The fifth scenario in `tests/browser_ui/form_browser_qa.mjs` uses the saved order
from the intake scenario, edits that same record in the browser, discards an
invalid raw decimal, saves repeatedly, then independently reopens SQLite and a
fresh form process. Its fixed screenshot is `order-editor-narrow.png`. The
existing reviewed branch, single sandboxed browser, loopback-only routes,
100-RPC limit, work/cleanup deadlines and redacted artifacts remain in place.
A test's presence is not evidence it ran: report results against the actual
source commit and inspect the screenshot before claiming browser acceptance.

Excluded: arbitrary imported forms, generic references, dynamic schemas/lists,
documents/posting/registers, conflict merging, migrations, crash-persistent drafts,
transport reconnect/replay, and native UI parity claims.
