# Local catalog editor (experimental U1/U2)

The optional Preact renderer now connects real scalar form events and bounded reference-row edits to detached
`CatalogObject.Write` and the admitted SQLite backend. This is a **bounded
application**, not a native 1C visual clone or support for arbitrary configurations.
The original `yadinassi-ui/0` read-only bridge remains unchanged.

## Run

With the Python package installed, use:

```console
yadinassi-catalog --f /path/to/application.sqlite
# Equivalent, including from the source tree:
python -m yadinassi.ui.local_app --f /path/to/application.sqlite
# Self-contained release executable (Windows: yadinassi.exe):
yadinassi --catalog-ui --f /path/to/application.sqlite
```

The file must already be a supported, active Yadinassi SQLite application. Use
the existing `yadinassi --create-db FILE --import-xml DIRECTORY` admission route
to create one from official Designer XML. A random SQLite file, missing file,
archived inactive configuration, `.1CD`, CF or DT is not an application.
**Selecting a writable file authorizes Save to change that file.** Develop with
owned copies, not a user's live database. Back up important application files.

The launcher prints a per-launch URL. Open that exact URL in a browser on the
same computer. Browser launch is opt-in (`--open-browser`). Stop with Close
database or Ctrl+C. The explicit `--catalog-ui` mode is included in standalone release executables.
Plain `yadinassi` still
runs BSL without a database, browser or server.

Prebuilt HTML/CSS/JS is shipped with the Python package. **Node/npm, a CDN and
internet access are not needed at runtime.** The browser only renders; it does
not execute BSL or access SQLite. The optional loopback plugin owns one child
runtime and proxies bounded NDJSON on stdin/stdout. The child owns the host-bound
SQLite context, BSL form session and detached catalog object. This is not the
future client/server transport or a remotely accessible database service.

## Working flow and honest limits

Choose a catalog, open or create a record, edit scalar values and bounded reference selections, Save, return to
the list, close the application and reopen the same file. Persisted values are
loaded again from SQLite, not a UI overlay. Strings, exact Decimal values,
Boolean and naive whole-second dates are supported. Numbers stay text in JS;
no floating-point or browser timezone conversion is applied. Qualifiers are
applied by the runtime, not guessed by the renderer.

- Fixed catalog references can be selected from a host-captured list of at most
  64 target records, plus the empty reference. Long choice labels are shortened
  with an ellipsis; UUID identities are unchanged. Deleted rows are not choices.
  Overflow, unavailable choices or a current dangling/deleted reference leave
  the field explicitly read-only and preserve its typed value. Close and reopen
  the card to refresh choices. Choices do not reserve target records or promise
  foreign-key/liveness guarantees against concurrent changes.
- This is a local host adapter, **not native reference FormData or a 1C picker**.
  Its scalar form stores a UUID selection key; the renderer sends a typed wire
  reference checked against the fixed field target and captured allowlist.
  Only the owning catalog manager builds the actual runtime reference on Save.
  Arbitrary UUIDs, wrong targets and raw strings reject without changing form
  state. Dirty, discard, revision/conflict, uncertain-write locks and durable
  refresh use the same path as scalar fields. An authoritative refresh containing
  a reference outside the captured choices stays locked for refresh; no false
  Saved state is reported. Large aggregate snapshots still fail closed at the
  existing message limit.
- Autoforms use real `FormAttribute`, `Items`, `Commands`, `DataPath`, `SetAction`
  and prebound BSL handlers. They are not imported managed forms. The closed host
  Save adapter is not a new BSL API, native standard Write or complete FormData.
- Scalar form state remains runtime-owned. The renderer sends a known control,
  finite event and typed input; never BSL, SQL, procedure names or database paths.
- Only the existing admitted ordinary-catalog configuration profile is supported.
  Object-module hooks, subscriptions, documents, registers, arbitrary forms and
  hierarchies are not silently skipped. Current list admission is bounded at
  1,000 rows and rejects overflow rather than silently truncating a catalog.
- There is no native GUI input/button/close parity claim. Earlier native evidence
  distinguishes actual create/open from directly called handlers. This adapter
  does not turn direct-handler observations into platform-dispatch evidence.

### Themes and desktop layout

The renderer starts in **Dark** mode, regardless of the operating-system theme.
The header's **Color theme** selector offers Dark, Light and System. System tracks
subsequent OS appearance changes. Only this choice is saved under the fixed
`yadinassi.catalog.theme` browser preference key. A blocked browser storage policy
falls back to Dark and does not interrupt editing. Session capabilities, records
and unsaved fields are never stored with the preference. Theme changes do not
send runtime events, save a record or discard its draft.

Wide desktop windows (at least 1,200 CSS pixels) use the available width for
catalog navigation, the record list and the editor side by side. The host still
owns a single editor and refuses navigation during editing. Those navigation
controls remain visible but disabled until the card is closed. The last loaded
list is explicitly labelled as a read-only **preview** and refreshes on return;
it does not pretend to reflect newly saved values. Reattaching directly to an
open editor has no cached list and shows a return-to-records placeholder instead.
No additional read or write API is introduced for this layout.

Medium windows put the editor beside navigation with the preview underneath.
At 760 CSS pixels and below the open editor takes priority and navigation/list
are hidden until return. Controls, long labels and reference text wrap, while
Save and Discard follow the fields and references in normal document flow, so
the action row never covers editable or read-only content. A new local edit hides
a stale success notice until the host reports the next outcome.

### Persistence, cancellation and failures

An editor retains one detached `CatalogObject` and its **original opaque row
revision**. List reads are operation-scoped and closed before writes. Save does
not reload the latest row first and erase a conflict. Conflicts/validation errors
leave the edit buffer intact; an unchanged repeated Save does not write again.

The object retains the exact operation identity and payload when a commit outcome
is uncertain. Editing and discard are locked. Resolve save outcome asks the same
object to reconcile that intent; it does not create a second record. When commit
is known but refresh failed, the next attempt only refreshes. Dirty clears only
after confirmed durable save, authoritative refresh and successful scalar-form
patch application. A refresh that cannot enter the bounded form keeps the editor
locked in refresh-only state; it never adopts a newer row revision early. Handler failures may
have already changed form state or the database: the reply includes the current
snapshot, not a false rollback promise. Snapshot failure explicitly marks state
unavailable and never reports Save success.

Back/Close runs ordinary cancelable close; dirty state remains open until the
user explicitly discards or saves. Discard does not write. A form close exception
leaves its authoritative state available. Transport loss **never auto-retries**
a write. Use Resynchronize while the same child is alive. A terminated process
loses unsaved drafts/session state; reopen the file and inspect persisted state
before attempting another create. Crash-persistent edit-session recovery is not
implemented.

## Local transport boundary

`yadinassi-editor/0` is a separate, provisional profile. JSON-RPC methods are
`editor.hello`, `editor.snapshot`, `editor.event`. Event names are exactly
`selectCatalog`, `create`, `openCard`, `page`, `change`, `command`, `closeCard`,
`close`, `addRow`, `deleteRow`, `changeRow`. Row events name a known section;
change/delete use an opaque host-issued row UUID, never a visible row number.
Every admitted event attempt advances the **editor sequence**, even
when its handler fails. This sequence is distinct from form and database
revisions. Invalid/stale envelopes do not dispatch. Replies are bounded, exact
integer IDs are required, and sessions cap requests at 4,096. Snapshots are full
replacements, not native form-delta synchronization.

The server binds only `127.0.0.1` on an ephemeral port. POST requires exact Host,
Origin, content type and a constant-compared per-launch capability; there is no
CORS. Only four exact static asset paths are served, no path traversal/file API.
Requests/responses and connections are bounded. CSP forbids external scripts,
frames and form submissions. There are no request logs or persisted credentials.
The launch capability is removed from the visible URL and retained in memory;
refreshing a tab requires reopening the printed launch URL. A new renderer reads
the same child snapshot rather than replaying an event. Do not share the launch
URL or expose this port. This protects the local browser boundary, not against
malicious processes/browser extensions already acting as the local user.

## Build and tests

`frontend/catalog/package-lock.json` pins official registry dependencies and
integrity values. Install with lifecycle scripts disabled:

```console
cd frontend/catalog
npm ci --ignore-scripts --no-audit --no-fund
node build.mjs
node --test test/*.test.mjs
```

`build.mjs` creates the committed assets and a SHA256 source/output manifest.
Preact's complete MIT license is shipped beside the bundle; esbuild's build-tool
license is retained in the frontend source. No node_modules or database fixture
is published. Runtime provenance includes every packaged asset and Python file.
The Python unit tests use authored XML and owned temporary SQLite files; they
cover real save/reopen, optimistic conflicts, exact uncertain intent, repeated
Save, cancel/close, authoritative failure snapshots and loopback security.
Actual browser QA is a separate gate, not implied by protocol unit tests.


### Reference-row sections (experimental host adapter)

Already-admitted logical SQLite schemas can now edit a tabular section with
exactly one fixed catalog-reference column. For example, a product with a
warehouse-reference section can add a row, select a warehouse, remove a row,
Save, and reopen the same database to see its persisted warehouse rows. Owner
fields and rows use the same detached object, optimistic revision and atomic
Write. This is real storage, not a preview or a renderer-only table.

The host captures at most 64 target records per column, excludes deletion-marked
choices and includes an empty reference. A current value outside those choices
is displayed read-only; its row can be removed explicitly. Choices do not reserve
records or add business rules: this autoform does not install object handlers.
In particular an empty or duplicate warehouse row is not automatically refused
by the original Номенклатура handler, which is not activated by this editor.

The editor admits at most 32 rows across the object's sections, subject also to
the existing full-message byte limit. Add/change is checked before adoption.
Other section shapes, unavailable choice sets and existing over-limit sections
have an explicit read-only summary and are preserved on scalar saves. They are
not truncated into an editable subset. There is no sorting or row reordering.

Row edits participate in dirty-close/discard, pending-save locks, authoritative
refresh, conflict detection and exact uncertain-write recovery. The browser
flushes scalar and row inputs before structural actions or Save; Discard does
not flush or write. Opaque row identity, rather than a shifting index, prevents a
stale row event from accidentally targeting the following row.

This does **not** activate the original imported Номенклатура or v6 tabular
capabilities. Its original fields, form handlers and pinned object source need
a separate admission/integration step. The original demo-directories profile is
unchanged. No native FormData, native GUI parity or arbitrary table-cell editing
is claimed.
