# Configuration-declared managed forms (opt-in host profile)

The configuration forms launcher loads a **trusted local Designer-style source
folder**, not a hand-written Python application package:

```console
python -m yadinassi.ui.configuration_app examples/configuration-forms/welcome --form CommonForm.Welcome
python -m yadinassi.ui.configuration_app examples/configuration-forms/counter --form CommonForm.Counter
```

The packaged executable selects the same launcher with
`yadinassi --configuration-ui CONFIGURATION_DIRECTORY`. Ordinary BSL CLI arguments
are unchanged; only the first argument selects this explicit mode.

The first application opens a second declared form from a BSL command and passes
a scalar Structure. The second calls a contextful server procedure which calls a
NoContext helper and synchronizes the resulting counter. They use the same host
and renderer, without application-specific Python registration.

An optional `--f existing.sqlite` opens a database only in the child server
process. The launcher never creates/imports a database implicitly. This is trusted
local application execution, not a sandbox for hostile BSL or a remote service.
The per-launch loopback URL is a private capability; do not share it.

## Source and executable boundary

Activation is explicit. This loader does **not** execute archived/inert forms in
an imported SQLite database. It reads bounded unchanged source bytes, admits
UUID ownership and declarations, and binds parent/client and child/server to the
same complete source digest before the first form allocation.

Supported declarations are `CommonForm.Name`, `Catalog.Name.Form.Name`, and
`Document.Name.Form.Name`. Forms must be declared by their metadata owner.
Only the admitted XML subset is executable:

- managed form metadata: Name and FormType;
- scalar attributes with String/Number/Boolean/Date types;
- InputField, LabelField, CheckBoxField and Button controls, including the
  bounded nested layout below;
- declared commands and OnChange, OnCreateAtServer, OnOpen, BeforeClose,
  OnClose handlers supported by the existing form session;
- ordinary scalar values, bounded immutable Parameters/Параметры.

Unsupported behavior-bearing XML is rejected, not ignored. Localized title
objects, automatic object forms, native standard commands, automatic persistence,
dynamic lists, arbitrary layout properties, and arbitrary FormData are not enabled by this
profile. This is not a claim that every Designer dump can already run.

## One BSL module, independent runtimes

The existing parser compiles each Module.bsl. The compiler admits declarations
only and creates detached side-specific ASTs. The client program never contains
server routine bodies. Contextful server routines can call server NoContext
helpers through the ordinary same-side runtime. Client NoContext calls use the
existing scalar InvocationPort and a separate server module. Contextful calls
use form replication and synchronize admitted form state before client BSL
continues. No second evaluator or browser-selected procedure exists.

Async and dual-context routines remain outside this profile. Remote endpoints
require explicit Val scalar arguments without defaults. The existing restriction
on directly passing a form attribute by name through a context crossing remains:
copy it to a local variable before the call. No form object or reference handle
is serialized as a parameter.

## OpenForm and lifecycle

Inside a client form handler:

```bsl
&AtClient
Procedure ShowDetails(Command)
    OpenForm("CommonForm.Details", New Structure("Message", Greeting));
EndProcedure
```

OpenForm/ОткрытьФорму accepts a declared form name and an optional scalar
Structure. Its current host profile is a procedure, not a returned form handle.
Owner/modal/uniqueness/callback options are not implemented. An intent is queued
until the current event has finished; nested event dispatch is never performed.
The new form has separate client/server objects and copied immutable parameters.
XML design exists before OnCreateAtServer; OnOpen runs only after the server
snapshot is admitted. A cancelled/failed opening retires the allocated session
and drops its queued child openings.

Up to eight forms can remain open, with at most 256 identities per launch.
Closed IDs are never reused. Duplicate browser open intents reuse their original
result; they cannot recreate a retired form. Switching tabs preserves raw local
drafts and focus without replaying BSL. Closing the application requires ordinary
close of every form, including hidden ones. BeforeClose cancellation is retained.
A lost or malformed response locks all forms. There is no automatic retry of an
operation with an unknown result.

The browser receives only admitted entry IDs, opaque session IDs, display data
and the existing closed form-event contract. It never selects source paths, BSL
routine names, database paths, or Python callbacks.

## Verification boundary

Python integration covers both XML applications, immutable parameters, source
mismatch, delayed OpenForm, cancellation, independent sessions, stale/duplicate
requests, NoContext and a real owned child process. JavaScript tests cover strict
responses, retained drafts, child discovery, close, identity retirement and
transport locking. Real-browser acceptance and the source-bound native regression
are separate evidence; unit tests are not evidence of native 1C window parity.

## Retained catalog list and command selection

The existing catalog workspace now refreshes the authoritative list after a
confirmed Save while keeping the editor open. It locates the saved identity in
the refreshed ordering, including after create/rename/deletion-mark changes.
If postcommit list projection fails, the card remains locked with a refresh
obligation; recovery rereads instead of repeating Write. Rejected or uncertain
saves never fabricate a list row from a draft.

List commands sit above compact rows. Plain click/Space selects one row;
checkboxes or Ctrl/Meta-click maintain an explicit visible-page UUID set. Open
and the existing card check require exactly one selection, not a row index.
Multiple selected rows do not trigger an implicit batch. The measured empty-ref
check remains a separate explicit “Проверить без выбора” command with no
selection. Selection is reconciled with catalog/page changes and authoritative
save results. The command resolves its target from current selection and the
latest snapshot before sending, even before the next render. Keyboard arrows
move row focus; Enter opens the sole selected row.


## Nested groups and tab pages

```console
python -m yadinassi.ui.configuration_app examples/configuration-forms/layouts --form CommonForm.Layout
```

The authored workbench demonstrates two pages, a horizontal name group, retained
raw edits, server summary calculation, and BSL group/page appearance changes. It
uses the same host as the other examples, without application-specific Python.
It is not a native-export fixture or evidence of 1C pixel/layout parity.

The additional XML subset is closed:

- `UsualGroup`: Title, Visible, Enabled, ReadOnly, Group (`Vertical` or
  `Horizontal`), ShowTitle and ChildItems;
- `Pages`: Title, Visible, Enabled, ReadOnly, PagesRepresentation (`TabsOnTop`
  only) and ChildItems containing one or more direct `Page` children;
- `Page`: Title, Visible, Enabled, ReadOnly, Group, ShowTitle and ChildItems.
  A Page is admitted only directly inside Pages; pages may contain nested groups,
  tables and further Pages. Existing field/reference/table/command admission is
  unchanged. Group/Page titles remain scalar strings, not localized objects.

Declaration order is retained, including buttons inside groups. In a nested
form, root controls also stay in declaration order rather than collecting every
button into a separate toolbar. Horizontal groups wrap at narrow widths. Layout
has at most 128 total nodes, eight levels, and globally unique item names and
numeric IDs across all child inventories. Topology is fixed by configuration:
programmatic Items.Add/Delete, reparenting, custom layout events, CurrentPage and
unlisted presentation properties are refused. The flat programmatic API remains
unchanged. Original XML/module bytes remain part of the complete source digest
and canonical profile verification; accepting layout does not add any storage,
standard-command, privileged-execution or native-service authority.

### Own properties versus effective restrictions

Groups are available through Items before OnCreateAtServer and OnOpen.
TypeOf returns the nominal FormGroup / ГруппаФормы type for UsualGroup, Pages
and Page, so BSL can inspect Items by type on either side. This does not enable
New FormGroup, dynamic Items.Add of that type, native type serialization,
CurrentPage or native inheritance semantics. Their
Title, Visible, Enabled and ReadOnly can be read and changed by admitted BSL on
either side. Each child's own flags are retained: changing a group never writes
its descendants' BSL properties. Effective Visible/Enabled are the conjunction
of a node's own and ancestor values; effective ReadOnly is their disjunction.
Removing a parent restriction therefore restores, but never elevates, each
child's own state. Replication transmits own properties and immutable topology;
the renderer projection derives effective flags. This is a specified bounded
host policy, not an assertion of measured native group-inheritance semantics.

Host event admission enforces effective Visible/Enabled on changes, commands,
table cells/selections and reference selection. Effective ReadOnly blocks input,
reference changes and commands in nested forms, while a read-only table may
still select rows for inspection. Trusted BSL may still assign data directly,
just as before; appearance is not a data-security boundary. Flat legacy command
dispatch semantics have not been changed by this feature.

### Renderer-owned page navigation and drafts

Page selection is private to one retained renderer view. No selected-page state,
BSL handler, CurrentPage value or event crosses the host boundary. Initially the
first visible enabled page is selected, or the first visible page if all are
disabled. A hidden/disabled selected page falls back by the same rule. Hidden
pages have no tab; disabled pages cannot be selected. ReadOnly does not prevent
navigation. Nested page selections are independent. Tab buttons support arrows,
Home and End and expose linked tab/tabpanel accessibility semantics.

Switching pages does not flush inputs, run BSL, refresh or discard drafts. Input
nodes, raw strings and selection ranges are retained, including invalid number
or date text. Pending edits on an inactive page block commands and Close before
any event is sent: return to that page and apply the edit (Enter or ordinary
blur), or explicitly Refresh to discard it. This avoids silently replaying a
hidden page's OnChange while acting on another page. Inactive, detached and
replaced DOM controls are fenced before dispatch; no intent is queued for later
page reactivation. Page switches are disabled while an event or reference picker
is in flight. A transport/outcome lock still permits local page inspection and
exposes retained raw scalar/cell drafts as selectable, whitespace-preserving
copy-only text. It never clears the lock, flushes a draft or retries an intent.
An authoritative change that removes, rebinds, disables, hides or
supersedes a pending edit preserves its raw text in copy-only recovery rather
than retargeting it. Existing transport-uncertainty locks remain unchanged.

These are distinct guarantees: the host rejects **BSL-hidden/disabled** controls
using inherited properties. It cannot reject a merely **renderer-inactive** page
as such, because no active-page token is sent. The latter is a browser interaction
contract, not a server authorization claim. Explicit refresh and form retirement
keep their existing draft-discard semantics. Page state is not persisted across
a browser reload or new activation.

### Evidence and native boundary

Host/unit coverage exercises strict XML topology, source identity, own/effective
properties, replication admission, catalog/document compositions and reference
restrictions. Renderer tests cover tab navigation, retained scalar/table drafts,
hidden-control dispatch, authoritative fallback and delayed responses. Real
browser acceptance is separate and must be reported for the exact tested tree.
No native window, tab-event, selected-page or responsive-layout parity is claimed.
Before adding native inheritance or CurrentPage semantics, acquire a bounded
source-bound 1C observation with a two-page form: record child own flags before,
during and after a parent visibility/enabled/readOnly toggle, capture which
controls remain interactive, and record event traces when switching with an
uncommitted edit. Do not reinterpret this renderer policy as that evidence.


Attachment-protected layout views opt into local read-only inspection only after
all retained clients are locked, all business requests are idle and no picker is
open. The wrapper remembers the generation in which this DOM was writable;
observer, generation/identity change, pagehide or closure revokes that inspection
grant. Busy/reconciling temporarily blocks it. Inspection only exposes local
page navigation and retained copy text. It never changes attachment.writable,
RPC refusal, takeover authority, the transport lock or queued-intent fencing.
Legacy consumers remain inert by default, and a failing inspection predicate
also leaves content inert. Disabled business inputs and actions remain disabled.
