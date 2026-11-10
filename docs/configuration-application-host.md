# Configuration application host and browser ownership

The explicit application host composes configuration-declared forms, client and
server CommonModules, and the managed application module. It is a local trusted
application runtime, not a browser BSL evaluator, a remote multi-user server, or a
claim of native window/lifecycle parity.

```console
python -m yadinassi.ui.configuration_app examples/configuration-application-host --application-host --open-browser
```

The example starts once after the client/server source handshake, calls
`Service.Add(7)` in the owned server process, and opens Welcome through the
client CommonModule `Tools`. Its Details command makes another real server call
and opens an independent form. Form close releases only that form, not the
application's other forms or shared scheduler. Close every form, then choose
**Close application** to run ordinary application exit.

## Execution and data boundaries

- One application-owned runtime family is constructed separately on each side.
  Server routine bodies are not present in the client activation. CommonModules
  retain their own context; they never inherit the current form's fields.
- The host binds a client OpenForm service before preflight and queues form opens
  only during admitted client dispatch. Failed startup or handler execution does
  not replay queued opens. Cancelled startup and BeforeExit cancellation are
  explicit states. A BeforeExit warning remains visible.
- Server CommonModule calls use the existing closed scalar invocation transport.
  The browser cannot choose a BSL procedure, file, database, or endpoint.
- Configuration source is canonically reimported with the explicit
  `configuration_application_v1` grant. Unknown behavior-bearing files and
  properties are rejected. The narrower standalone form and CommonModule
  profiles do not acquire this authority implicitly.
- Catalog Object forms, when included in this composed profile, remain flat
  scalar catalogs. Hierarchy, reference fields, tabular sections and documents
  are not silently enabled. An existing database must carry the matching source
  and profile; startup does not create or migrate it.

A successful transport response is not a general business transaction. Existing
catalog write/receipt rules still apply. After an uncertain response the host
locks instead of claiming rollback or retrying a write.

## One writer, several browser tabs

`--application-host` enables browser attachments. The older catalog, form,
Orders workspace and reference Orders launchers can opt in separately with
`--browser-session`; their default legacy protocol is unchanged.

The first attachment controls the application. Opening the complete launcher URL
in another tab attaches an observer, not a second writer. **Take control** is an
explicit ownership transfer. A generation fence rejects the previous writer
before business dispatch; transfer cannot interrupt an already admitted RPC.
A known ownership refusal is recoverable. An unknown business outcome is not a
retry instruction.

Reload uses a narrow, origin-scoped resume capability in `sessionStorage` and
reconciles authoritative host state. The full launcher capability and RPC
credential are not persisted. Do not share the original launcher URL. An
observer does not run business initialization until it obtains control.

Unsubmitted or invalid input remains only in its original live document. It is
not a durable browser draft and is not restored in a new tab or after document
destruction. Where ownership or row identity changed, a retained draft is
copy-only rather than being retargeted or automatically submitted. Resolve or
copy it before closing the original page.

## Closing a tab is not Save or Discard

Page hide sends only an advisory detach. Heartbeats use a 90-second lease; after
all attachments are gone there is a 30-second grace period. Missing detach or a
suspended browser can therefore delay cleanup. No callback runs solely because
a tab became hidden.

The server then asks its ordinary close policy whether shutdown is safe:

- pending browser input, uncertain work or pending runtime tasks retain the host;
- the configuration application retains open forms and honors BeforeExit refusal;
- old editor modes require a known clean snapshot, generic forms require an
  explicit trusted dirty-state contract, and workspaces require no open forms;
- a refusal is retained rather than repeatedly running BeforeExit on every tick.

There is no automatic Save, Discard or forced data-loss timeout. A retained host
may need explicit recovery or operator shutdown if the original page is gone.
Confirmed SQLite data remains durable; raw browser-only input cannot be recovered
by keeping the Python process alive. A clean successful close terminates the
owned host and child process; another tab must start a new launcher afterwards.

The attachment limit is bounded to 256 per host lifetime. This is deliberately a
single-user local ownership protocol, not an account, authentication or
collaboration system.
