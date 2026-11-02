# Third track: a usable catalog application, with 1C-compatible programming

The goal is an application that opens a supported existing file database and lets
people work with its catalogs. Compatibility of **programmatic** forms, elements,
data and events matters more than pixel-identical drawing. A read-only viewer or
an in-memory form edit is an intermediate milestone, not the completed MVP.

## Architectural direction

- The Python interpreter owns form definitions, state, event bindings and BSL.
- Both logical BSL client/server contexts remain in the interpreter. A browser
  renderer does not imply `WebClient` preprocessing or remote BSL execution.
- Optional separate renderer process; JSON-RPC/NDJSON on stdio. The first visual
  renderer is Preact + HTML/CSS with prebuilt assets; Node is build-time only.
- A future local browser bridge can own HTTP/WebSocket dependencies. None are
  required by the core. Local origin/session authentication and loopback-only
  binding must precede a network implementation; this increment has no listener.
- Tauri/native window integration and other production renderers are later. A
  small independent protocol client already tests the replacement boundary.

Do not postpone the 1C form semantics until after multiple renderers. Establish
that model alongside the first vertical slice, and keep renderer component APIs
out of BSL. Official background: [form module context](https://1c-dn.com/library/tutorials/practical_developer_guide_form_module_context/)
and [form data types](https://1c-dn.com/library/tutorials/practical_developer_guide_form_data_types/).
Form attributes and module variables are different; form data is not just an
applied CatalogObject or a JSON dictionary.

## Audited starting point

At base `6cb6fb0d3d661c394d3744e2293e953af6acf989` (tree `92d24faf`):

| Area | Existing evidence / missing dependency |
| --- | --- |
| Offline access | `database_context.py`: O_RDONLY per call, no native session/lock |
| Catalog reads | `catalogs.py`, `catalog_types.py`: managers, immutable refs, exact lookup, bounded cursor |
| Mixed cards | `CatalogCardField`, `docs/linked-catalog-cards-next.md`: S/N/B/D/fixed catalog ref |
| Schema | `storage/catalog_metadata.py`: names/UUIDs; attribute binder retains types/qualifiers |
| Existing 1C forms/modules | No CONFIG form/module loader; unknown attribute-parser subtrees are opaque |
| Form context | `_new_server_activation` explicitly is not a form context |
| Transfer | `_copy_context_packet` has a measured bounded contract, rejects catalog refs/FormData |
| Module receiver | `ThisObject` currently is `_Module`, not a ManagedForm |
| Lifecycle | Scheduler has run-until-idle/close, but no prebound host form-handler API |
| Writes | No CatalogObject/CreateItem/GetObject/Write, transaction, allocator or index writer |

The managed compilation profile is not a form implementation (the existing
compilation-profile tests reject `New Form`). Launcher `Form.xml` is input to
native 1C tests, not a yadinassi form loader.

Before publication the first UI candidate incorporates actual main `d889cb53`
(XDTO/periodic union). Its four optional UI Python files are included in native
runtime provenance: 117 -> 121, with exact inventory/byte-drift tests updated.
No source is excluded and no native report/file-count cap is raised.

Existing read admission remains narrow: 64 MiB catalog images, bounded rows/slots,
restricted code ordering, flat supported schemas and limited free-slot layouts.
Do not promise that an arbitrary real configuration is supported. An unsupported
schema/read budget is not automatically evidence that the database is corrupt.

## Small increments and their acceptance

1. **Headless catalog foundation (this increment).** Typed wire values, immutable
   view/card snapshots, source-generation checks, capability report and finite
   navigation; actual FileDBContext parsing and independent stdio client. No
   BSL UI API or GUI is claimed. See [protocol v0](ui-protocol-v0.md).
2. **FormRuntime, immediately next.** Bound form module/context, scalar form
   attributes, element/command identities, binding and finite event dispatch.
   A public host invocation path must call resolved routines directly, never
   concatenate BSL source. Keep standalone `ThisObject` behavior intact.
3. **Minimal Preact renderer and persistent session.** Catalog chooser/list/card,
   typed input, focus/keyboard basics, validation/cancel/close, message display,
   bounded table pages, reconnect snapshot. No business logic in JavaScript.
4. **Durable catalog write integration.** Detached CatalogObject/draft, validation,
   commit capability and real storage writer; then create/write/deletion mark.
5. **Packaged usable application.** Host-selected existing offline supported DB,
   readable capability failures, reopen persistence and independent native 1C
   readback. Only this closes the functional application MVP.

The first declared profile should reuse flat Products/Categories, distinct
fixed-width digit String codes, Description, String/Number/Boolean/Date fields
and a fixed catalog reference. Names and UUIDs must come from metadata, not fixture
constants. Product/category names here are illustrative. Owned synthetic fixtures
are development input, not the only accepted product input.

Keep backend and UI connected through schema/capabilities, read snapshots, detached
draft, validate and commit operations. Until a real writer exists, commit refuses
and the UI never reports Save success. Detached draft behavior can be added without
claiming native object events or persistence. Auto-generated forms must be labeled
as such; importing arbitrary existing forms is a separate capability. Never silently
bypass custom form/object logic with an autoform to enable writes.

## Native form probe specification for the next increment

Choose an explicit existing measured target/profile (initially managed-thick-file
on Linux 8.3.27.1508); browser rendering does not change that BSL profile. Stage a
small owned form and literal BSL module, with source/module/redump hashes and
typed observations. First record, then implement; do not fabricate native outputs
from the host model. A probe must distinguish direct handler calls from actual
platform-generated events. See [Developer Guide, chapters 7.7–7.9](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293).

First discriminators:

- Form attributes vs client/server module variables, direct-name resolution and
  `ThisObject`, two independent form instances, close/reopen lifetimes.
- Items/Commands identity, DataPath binding, scalar property changes, inherited
  visibility/availability/read-only state; no pixel parity requirement.
- A dynamically added attribute, element and command: server-side availability,
  subsequent access rules and command/action binding.
- Creation/opening sequence and cancellation; input commit vs programmatic
  assignment vs direct OnChange invocation; command and cancellable close.
- Context-bearing server call updates form data; NoContext cannot access form
  state. Preserve existing ordinary parameter-transfer rules separately.
- Escaping/caught errors, exactly-once dispatch, cancelled actions, repeated
  clicks, stale events, closed elements and pending asynchronous work.

Object references/FormData conversion and the complete write-event pipeline are
separate bounded measurements. Simply calling OnWriteAtServer is not a platform
write transaction. Enforce source-bound host/native equality, independent evidence
audit and the existing four-platform/Ready gates for any claimed native semantics.

## Durable writes: the actual critical path

Existing `_VERSION` bytes are opaque; physical indexes, allocator and write/lock
semantics are not implemented. Even same-length row updates cannot be treated as
safe patches. Working-copy/copy-on-write publication simplifies rollback but does
not establish correct versions, indexes, page ownership, free lists or ID allocation.

Develop only against owned disposable actual `.1CD` copies. First measure native
before/after images and metadata for one existing-card update, failure/rollback
and reopen; implement that narrow path; then creation and deletion mark. Preserve
the original, reject conflicting/changed sources and prove the resulting image
through both readers. Do not modify a user's real database without authorization
for the particular target.

General configurations also require object modules, subscriptions, validation and
their dependencies to execute or to fail closed as unsupported. Physical format
integrity alone is not business compatibility. A native-1C write bridge, if later
chosen, must disclose its installed-1C dependency; it is not a standalone writer.

MVP completion requires change -> save -> close -> reopen in yadinassi and native
1C, reference identity preserved, validation/cancel/failure behavior checked, no
silent duplicates and no changes on failed commit. A JSON protocol, browser shell,
green unit test, sidecar or in-memory object alone cannot satisfy that criterion.

## Coordination

Core track owns form context, prebound routine dispatch and measured FormData/ref
transfer. Database track owns durable object/write integrity and metadata admission.
UI track owns protocol/session/rendering and the integrated user flow. Full XDTO,
full Query/СКД, document/register writes and multiple production renderers should
not block the minimal catalog slice. Reconcile exact current-main source before
publication; never reuse a previous runtime bundle's native evidence for a union.
