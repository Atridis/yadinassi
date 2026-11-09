# Bounded managed-form runtime: local preparation

This is a new **headless core** subset, not a browser renderer or visual 1C clone.
No native form acquisition has run for this source. Local interpreter replay is
not a platform event result. The UI catalog browser is a separate adapter and
its session is not a logical BSL client.

## End-to-end slice

`FormSession` accepts a trusted application module, bounded scalar attribute
schema/initial values and fixed lifecycle bindings. Renderer input can select
only `change`, `command`, or ordinary `close`, on a known control and exact
revision. It cannot supply BSL source, a procedure name, a side or a signature.
The session invokes prebound procedures with host values and internal reference
slots, not generated BSL/AST strings. This API is internal Python integration,
**not an invented BSL global**.

The BSL model includes `ThisObject`, `Items`, `Commands`, `FormAttribute`,
`ChangeAttributes`, `GetAttributes`, form/field `SetAction`, field `GetAction`,
flat input/checkbox/label fields and command buttons. Composition and action
binding require server context. `DataPath` is server-only and set-once. Dynamic
attributes are available through `ThisObject.Name`, not unqualified module
locals. Metadata-predeclared scalar attributes support unqualified access.
Descriptor mutation is detached from the already-installed attribute schema.
`FormField.Type` is the English property for Russian `Вид` (not `View`).

Opening runs the server create handler then client open handler. The bounded
host models input, commands and cancelable close with serialized execution;
**automatic native input/command/close dispatch is still unmeasured**. Handler
errors retain completed mutations and advance the revision; callers must fetch
a new snapshot. There is no promise to roll back arbitrary BSL or database side
effects. Reentrant/concurrent dispatch and snapshots during a handler reject.
BSL `Message` is captured separately, never written into a stdio RPC stream by
default. Optional host output callbacks are trusted application infrastructure.

## Explicit limitations

- !todo CatalogRef form-context transfer is not admitted until measured. A UI
  card may retain its scoped reference identity outside the scalar BSL form.
- !todo Native automatic change/button dispatch and canceled create/open/close
  need genuine platform dispatch evidence, not direct procedure calls.
- !todo Non-Val unqualified form-attribute transfer explicitly rejects. Generic
  interpreter copy-in/out, Date/Null restrictions and reference rejection are
  unchanged; a form is not a general relaxation of that boundary.
- !todo No ordinary forms, nested groups/tables, dynamic lists, standard Save,
  stored-data locking/dirty prompts, modal windows, async dialogs or shutdown
  (`Exit=True`) semantics. `StandardProcessing=False` or non-Boolean rejects;
we do not silently run unsupported standard processing as though it were True. `StoredData=True` rejects instead of pretending to
  persist or lock. Programmatic `Close()` is not exposed yet.
- This is not an untrusted-code sandbox: a trusted BSL application retains the
  interpreter's existing capabilities. The renderer never receives those APIs.

## Local budgets (not claimed platform maxima)

Module 65,536 characters; 128 scalar attributes, 128 live items, 64 live commands;
1,024 installed dynamic attributes plus created items/commands over the session;
this ledger excludes the separately capped128 predeclared attributes and detached
`FormAttribute`/`GetAttributes` descriptors (ordinary BSL allocation/AST limits apply); 10,000 events; 100,000 visited
AST nodes per event; 65,536 characters per scalar text and 262,144 total scalar
text; bounded exact Decimal admission (128 coefficient digits after a bounded
CPython allocation check); titles 1,024 characters; 64 messages/event with
4,096 characters/message. Field/command records and snapshots are immutable
scalar tuples, not exported object handles. Existing parser and builtin
allocation limits also apply; the AST-visit budget is not a universal wall-time
or memory sandbox for every existing builtin.

## Primary evidence

Official EDT2026.2 `com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`,
SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
recovered from the existing pinned official URL. Relevant help paths under
`SyntaxHelperContext/objects/catalog1649/`:

- `catalog1890/ClientApplicationForm/methods/ChangeAttributes3981.html`,
  `GetAttributes4030.html`, `SetAction3998.html`;
- `catalog1890/ClientApplicationForm/events/OnCreateAtServer327.html`,
  `OnOpen328.html`, `BeforeClose330.html`, `OnClose331.html`;
- `catalog1890/FormAttribute/ctors/ctor144.html`;
- `catalog1890/FormAllItems/methods/Add4007.html`;
- `catalog1890/FormCommands/methods/Add4013.html`;
- `catalog1890/FormCommand/properties/Action8738.html`;
- `catalog1676/FormField/properties/DataPath8729.html`, `Type7117.html`,
  `methods/SetAction4000.html`, `GetAction3999.html`.

Official [SSL integration examples](https://kb.1ci.com/1C_Standard_Subsystems_Library/Guides/1C_Standard_Subsystems_Developer_Guide/Chapter_2._Library_integration_guide/)
show the extra `Item` parameter for field handlers and `Command` for local
command handlers. These examples establish calling conventions, not acquisition
of our automatic dispatcher. The [official developer guide](https://1c-dn.com/download-trial/files/guides/developer_guide.pdf)
distinguishes direct event-handler calls from platform-dispatched events and
the surrounding standard operations.

## Native source checkpoint — not dispatched

`scripts/form_runtime_packet/` contains a fixed 40-record module and managed-form
XML. Explicit server/client directives are preserved; the ordinary all-client
helper injector must NOT process this source. The local parser caps source at
8,192 bytes and observations at 4,096 bytes, exact 40 ordered ASCII values of at
most64 characters. `!E` is an action-error observation, never availability success.
No raw exceptions, paths, auth data or run-learned dictionaries are exported.

The packet covers composition, bindings, defaults, attribute/field/command
mutation, lookup/removal, server create→client open and contextful scalar calls.
Cases31–34/37/39–40 are explicitly **direct handler calls**, not automatic events.
The source does not write a file, operate on a database or launch anything.

Before the first native run, a separately reviewed closed route must bind actual
re-dumped managed-form metadata (DefaultForm + managed type + these event names),
exact module/source hashes, an owned finite output writer and process lifecycle/
cleanup. Merely accepting the local XML or `#If Client` is insufficient. The
current generic `client_wiring` validator correctly permits only its historical
OnOpen route and must not be weakened. The integrated candidate adds one closed form-only workflow job and runner, using the existing image, process deadlines and read-only job permissions. It does not change triggers, credentials, source/output caps or the old OnOpen-only route. No native session has run yet; the integrated runner needs its own final review before dispatch.

## Closed native lane and evidence boundary

`native_1c_form_runtime_profile.py` stages exactly 22 public inputs into a
read-only mount of the existing pinned native image. The new
`--form-runtime-suite` selector is separate from every paired tree profile.
The existing fresh database/security/bootstrap gates still run first. A fresh
owned EPF is built from the pinned Form XML and mixed client/server module,
then re-dumped and checked before execution. Unknown XML normalization,
namespace relocation, extra files or altered main-attribute metadata fail
closed; no historical OnOpen-only check is relaxed.

The platform creates/opens the managed form. A nonce-bound request and two
fixed markers bind its 40 bounded observations to the reviewed source and XML.
Actual create/open traces are distinct from explicitly direct change/command/
BeforeClose handler calls. This is not proof of real button/input dispatch or
platform cancellation semantics. Those remain `!todo` until a genuine native
UI-event mechanism is measured.

The native process retains the existing 120-second deadline, exact process
identity/session-bus checks and final census. Fixed generated files remain in
owned container tmpfs; host acceptance requires verified container removal and
private staging cleanup. The public artifact contains only bounded fixed test
observations and validated finite provenance, never raw native errors, logs,
request paths or credentials. Failure reports contain only closed phase/reason
and boolean witnesses. A successful native observation is separate from
interpreter equality; neither has yet been measured for this candidate.

### First acquisition and failed-only re-dump diagnosis

The first source-bound run rejected the generated re-dump with
`module_mismatch` in phase `redump`, before the managed ENTERPRISE invocation.
No entered/completed observations were available; this does not establish a
runtime semantic mismatch or its precise normalization cause. The original
failure receipt is preserved separately.

A bounded failed-only structural projection can now distinguish inventory,
metadata, Form XML and module checks. It exports only known-file presence bits,
a capped extra-entry count, at most32 numeric-ID XML rows and root/source-owned
namespace/literal IDs, with all unknown regions redacted to0. No raw XML,
unknown identifiers/values, paths or error text escape. Whole owned Form XML
SHA256 is provenance only. DTD, non-UTF8, oversized/deep input and projection
budgets fail closed. The strict original re-dump validator remains authoritative:
a diagnostic never substitutes a source witness or allows ENTERPRISE execution.


### Measured re-dump equivalence (not yet ENTERPRISE semantics)

The failed-only native projection established all five owned files and exactly
11 known Form nodes. The observed serializer changes were root version2.20,
OnOpen/BeforeClose/OnCreateAtServer event order and17 root declarations instead
of3. The raw re-dumped XML was not retained; its whole-file SHA and numeric
projection are historical evidence, not a reconstructed-byte claim.

Admission now treats only versions2.4/2.20 and the exact three unique event
name/handler bindings as serialization-equivalent. Extra root-only namespace
declarations must be unused; lexical tag/attribute prefix inspection rejects
active extras. Exact default/cfg/v8 bindings and all expanded nodes, attributes,
IDs, QName-valued text and handler names remain fixed. Nested/shadow namespaces,
duplicate events, new behavioral nodes, changed main attribute/type and other
versions still fail. Runtime and observer BSL are unchanged. This correction
still requires a fresh source-bound native40 run before any parity claim.

## SQLite composition and opt-in client/server boundary

This source composes the managed-form slice with the SQLite catalog backend and
retains the separate official-XML CatalogObject behavior profile. It does not
restore physical `.1CD`/CF/DT readers, fixtures or oracle routes. The form oracle
uses only owned official XML/EPF operations and one native client session.

The absolute CLI default remains plain BSL execution without a database or
server. `--f <path>` explicitly selects the local SQLite/thick-client mode; it
does not implicitly create a file or require UI/network. Future client-only and
server-only modes require separate explicit options, not yet defined here.

The current FormSession is a local logical-context implementation, not a remote
protocol: fresh server activations still share the local form model. The opt-in
[replicated scalar form host API](form-replication.md) implements Replicated Form
State with distinct logical client/server copies, prebound typed signatures and
a host-supplied byte exchange (which can be local direct transport),
dirty-delta admission before a contextful server call and response application
before dependent client BSL resumes. No-context calls transfer arguments only.
Server revision, client sequence, request ID and backend record revision remain
distinct. UI focus/cursor are local; connections/transactions are server-only.
No renderer-selected procedure names, Python object handles, pickle, server
routine bodies in client artifacts or implicit networking are admitted.

The first independent transport step is the [scalar NoContext InvocationPort](invocation-port.md):
plain client BSL can call a prebound server function through a byte exchange and
resume with its result, including across a separate process. That opt-in embedding
API carries no form state and does not change FormSession's shared local model.
The host may also call `port.bind_form(session, binding)` before open. A client
handler can then pass explicit scalar `ThisObject.Attribute` expressions to a
prebound NoContext endpoint and use the result before the event snapshot returns.
The event gate remains held across the exchange, and stale clicks cannot repeat
it. Form ownership, local contextful handlers and renderer routing are unchanged;
this is not contextful form replication.

The detached-copy/barrier API is separate from local FormSession and has focused
synthetic byte-transport tests. Neither those tests nor logical activation prove
exactly-once writes, exception rollback or automatic native UI event parity.
MessagePack/WebSocket, authenticated module caching and remote resume are future
transport choices, not dependencies or capabilities added by this slice.

## Closed application actions (local integration)

Trusted Python infrastructure may install immutable `FormApplicationAction`
descriptors at session creation. Each binds one command and expected BSL handler,
a finite scalar input/output schema, one host callback and an optional fixed
post-application acknowledgement. The renderer cannot
register/select callbacks, methods or sides. Dispatch checks the binding both
before and after the ordinary BSL handler. Rebinding cannot redirect a capability.
The callback returns `FormActionResult`; the whole scalar patch is preflighted,
then applied shrink-before-growth with the existing form member API inside the
serialized event. Only successful application invokes the fixed acknowledgement;
the result payload cannot provide a callback.
Exceptions retain preceding effects and advance the form revision. No rollback
of a completed database operation is implied by a later callback/patch failure.
This is internal application integration, **not a native BSL form method**, and
must not be used to claim standard Save/FormData semantics. The catalog editor
keeps references outside the scalar form and uses detached CatalogObject.Write.
`FormSnapshot.item_views` adds field-view metadata without changing the existing
`items` tuple shape. See [the editor contract](catalog-editor.md).
