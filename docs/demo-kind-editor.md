# Original demo kind editor (bounded local adapter)

Goal: open the original `ВидыНоменклатуры` form, edit Description, execute its
original OnChange and BeforeWriteAtServer handlers, allocate its code, save to
SQLite, close and reopen the persisted record. This is a local host form adapter,
not native 1C managed-form parity or completion of all twelve demo scenarios.

## Active storage boundary

- A fresh explicit v6 import retains the entire original configuration archive.
  Existing v5 archives remain permanently inert and are never upgraded in place.
- Only the completely admitted original kind catalog is active. Products and
  warehouses remain explicitly unsupported, not silently rewritten or discarded.
- A closed active catalog metadata profile must validate all operative settings.
  The current static form analyzer alone is insufficient: some metadata leaves
  it accepts are explicitly non-operative projections.
- `active_form_catalogs()` returns an immutable tuple of admitted UUIDs.
  `read_form_source(catalog_id, expected=identity)` returns the existing exact
  frozen source DTO only for the admitted catalog.
- The backend pins the complete archive manifest and active schema at open.
  Every write transaction checks the pin before any mutation under BEGIN
  IMMEDIATE. UI source identity is compared with that same backend pin. A new
  backend cannot replace the controller's backend to resolve an old intent.
- Read-only source observations are not write authorization. A changed unrelated
  retained file, generation, catalog metadata, form metadata or handler source
  invalidates new writes; restoration must not silently revive a stale editor.
- Pending receipt resolution is not a new write. Source drift must not erase an
  existing durable receipt or cause an already submitted intent to be replayed.

## UI implementation

The existing CatalogEditController retains its object and recovery state machine.
The `imported_form` flag is host-only and not exposed to any renderer request.
CatalogEditorApplication derives it from `active_form_catalogs()`. No request can
supply source, handler, identity, path or the flag.

The controller pins the exact source record on open and validates admission
without running handlers. Code is read-only in the renderer and rejected by the
host input route. Description changes use a fresh verified detached draft from
the current authoritative buffer, then adopt the normalized scalar value and
bounded field messages only after source verification. A failed detached event
leaves the displayed buffer untouched. No independent mutable draft survives
between events.

An ordinary Save runs the original BeforeWriteAtServer before object setters and
Write. Refusal preserves edits, does not write or allocate a code, and displays
its field message. Successful Write follows the existing refresh/adoption path.
Pending commit or refresh takes precedence over source preparation: neither
branch reruns BSL or substitutes current values for the retained write intent.
Dirty Close is refused; explicit Discard closes without writing. Source changes
lock further input/save while preserving the buffer. Discard after source
invalidation closes the whole database without attempting stale inventory reads;
reopening a card on the same immutable source pin is not a recovery strategy.
A cheap backend-object identity check precedes pending recovery, without BSL or
source reads. Source integrity failures also permanently invalidate the editor.
Repeated Save still runs original validation but skips an unchanged database Write.

The renderer displays original handler messages as escaped text, never HTML, and
labels the bounded host adapter honestly. Native parity remains false.

## Run the bounded demo

From the repository root, create a new disposable database from the original
retained fixture (the destination must not exist):

```python
from pathlib import Path
from yadinassi.sqlite_catalog import SQLiteCatalogBackend
root = Path("tests/fixtures/demo_cf/source")
files = {p.relative_to(root).as_posix(): p.read_bytes()
         for p in root.rglob("*") if p.is_file()}
backend = SQLiteCatalogBackend.create_demo_kinds("demo-kinds.sqlite", files)
backend.close()
```

Then launch `python -m yadinassi.ui.local_app --f demo-kinds.sqlite` and open
its printed local session URL. Select `ВидыНоменклатуры` and create a record.
Code is read-only. Edit Description and leave the field to run original OnChange;
Save runs original server validation. A short name is refused without allocating
a code; a valid name is trimmed, numbered and persisted. Close and reopen the
record/database to see the stored value. Other original catalogs are not active
in this slice; their source files remain byte-for-byte retained.

Moving directly to Save/Back/Close uses that command's flush instead of racing a
blur request. Discard does not flush. Failed change requests preserve local text.
Field messages are displayed as escaped text, with no inferred field-navigation
semantics.

## Verification and limits

Fourteen original-demo UI integration tests plus 44 existing controller,
protocol and commit-cleanup tests passed normally and under `python -O` (58 per
mode). They cover real v6 creation, original handlers, read-only Code, refusal,
normalization, durable save/reopen, numbering, dirty close/discard, real persisted
source drift and restoration, historical uncertain receipt recovery, refresh,
backend replacement in both pending states, and stale discard through protocol.
An independent static composition review cleared the controller/DB/renderer
recovery paths. The renderer's existing 20 JavaScript tests pass and its locked
asset build succeeds. Asset provenance checks run separately against generated
outputs. No browser interaction run, screenshot, native 1C managed-form parity,
full-product editing, or all-twelve-scenario completion is claimed here.

Commands:

```sh
PYTHONPATH=tests:. python -m unittest test_imported_kind_editor test_catalog_editor test_catalog_editor_protocol test_catalog_commit_cleanup_recovery
PYTHONPATH=tests:. python -O -m unittest test_imported_kind_editor test_catalog_editor test_catalog_editor_protocol test_catalog_commit_cleanup_recovery
node --test frontend/catalog/test/*.test.mjs
node frontend/catalog/build.mjs
PYTHONPATH=tests:. python -m unittest test_ui_asset_provenance
PYTHONPATH=tests:. python -O -m unittest test_ui_asset_provenance
```
