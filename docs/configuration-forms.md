# Configuration-declared managed forms (opt-in host profile)

The configuration forms launcher loads a **trusted local Designer-style source
folder**, not a hand-written Python application package:

```console
python -m yadinassi.ui.configuration_app examples/configuration-forms/welcome --form CommonForm.Welcome
python -m yadinassi.ui.configuration_app examples/configuration-forms/counter --form CommonForm.Counter
```

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
- flat InputField, LabelField, CheckBoxField and Button controls;
- declared commands and OnChange, OnCreateAtServer, OnOpen, BeforeClose,
  OnClose handlers supported by the existing form session;
- ordinary scalar values, bounded immutable Parameters/Параметры.

Unsupported behavior-bearing XML is rejected, not ignored. Localized title
objects, automatic object forms, native standard commands, automatic persistence,
layout groups, dynamic lists, and arbitrary FormData are not enabled by this
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
