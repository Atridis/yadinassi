> The optional scalar editor/renderer is now implemented as a bounded next slice;
> see [catalog-editor.md](catalog-editor.md) for the current executable contract.
> Historical read-only foundation limitations below describe `yadinassi-ui/0`,
> not the separate `yadinassi-editor/0` adapter. Full native managed forms and
> reference editing remain outside this slice.

# Third track: a usable catalog application, with 1C-compatible programming

The goal is a working application over a yadinassi SQLite database containing
configuration, BSL source and application data. Configuration interchange uses
the platform's official XML export/import. Programmatic forms, elements, data
and events matter more than pixel-identical drawing. A read-only viewer or an
in-memory form edit is an intermediate milestone, not the completed MVP.

The SQLite direction supersedes the former native-file-format roadmap. There is
no binary configuration/archive/database import or physical-format fallback.
Existing native application data migration is not part of this increment.

## Architectural direction

- The interpreter owns form definitions, state, event bindings and BSL. Both
  logical BSL client/server contexts remain in the runtime, not JavaScript.
- A renderer uses finite events and typed snapshots. No arbitrary procedure
  name, source code, SQL, database path or transaction handle arrives from it.
- The first visual renderer remains Preact + HTML/CSS with prebuilt assets;
  Node is build-time only. Headless JSON-RPC/NDJSON is the present foundation.
- The UI consumes the logical catalog port, not SQLite connections or storage
  internals. Local deployment uses a host-selected SQLite database. The intended
  server deployment gives only yadinassi_server access to that database; clients
  use a service boundary. That network service, authentication and authorization
  are not implemented by the current stdio example.
- Optional browser HTTP/WebSocket integration must establish local origin/session
  authentication and loopback policy before adding a listener. Tauri, other
  renderers and other database engines are future extensions, not dependencies
  of the first local application.

Form semantics must not wait until multiple renderers exist. Form attributes and
module variables are different; form data is not simply a CatalogObject or JSON
dictionary. See the official [form module context](https://1c-dn.com/library/tutorials/practical_developer_guide_form_module_context/)
and [form data types](https://1c-dn.com/library/tutorials/practical_developer_guide_form_data_types/).

## UI/backend boundary

`yadinassi/catalog_backend.py` defines logical schema, keys, snapshots, revisions,
capabilities and read/write operations. The DB track owns persistence, configuration
admission, atomicity and recovery; the runtime owns BSL object identity, defaults,
assignment, handlers and validation. UI owns presentation, navigation, eventual
edit buffers and dirty/cancel/refresh behavior.

The headless catalog repository uses a pinned read view, metadata-derived names,
bounded logical rows and immutable view/card DTOs. Its read-only bridge closes
owned resources on normal close, EOF and failure. Database identities scope
references internally; UI navigation revisions are not database revisions or
native DataVersion. Declared backend ordering is not a native collation claim.

The current UI route has `canEdit=false` and `canWrite=false`, even when an
underlying backend supports writes. No UI Save handler is enabled by a capability
flag alone. `commit()` refuses rather than publishing a sidecar, overlay or
in-memory Save success. See [protocol v0](ui-protocol-v0.md).

## Small increments and acceptance

1. **SQLite read integration.** Host-selected existing database, catalog chooser,
   list, card and linked reference through the logical port. Ordinary owned
   SQLite fixtures, independent subprocess client, bounded errors, lifecycle
   cleanup, schema/identity rejection and reopen checks. No binary image fixture.
2. **FormRuntime and native behavior.** Bound module/context, scalar attributes,
   Items/Commands, DataPath, finite prebound dispatch and cancellable lifecycle.
   The host invokes resolved routines, never concatenated BSL source. The
   standalone module ThisObject behavior remains distinct from a form receiver.
3. **Minimal Preact renderer.** List/card navigation, typed input, focus/keyboard,
   validation/cancel/close, readable errors, bounded pages and resync. Business
   logic stays in the runtime. Read-only state must be visibly labeled.
4. **Actual write flow.** Create/edit draft -> validation -> confirmed atomic
   backend commit -> refresh. Dirty clears only after durable success. Cancel,
   conflict or validation failure does not falsely report Save; an ambiguous
   commit is resolved by its backend receipt, never a blind retry.
5. **Packaged local application.** Import an admitted official XML configuration;
   store configuration and code in SQLite; remove the import directory; close
   and reopen; list/read/create/edit/cancel/save/reopen successfully. Only this
   integrated user flow closes the bounded functional application MVP.

The first profile is flat catalogs with explicit string codes, Description,
String/Number/Boolean/Date attributes and fixed catalog references. Names and
UUIDs come from configuration, not example constants. Products/Categories are
illustrative test names, not the only supported application.

Unsupported configured business handlers, subscriptions or forms must be reported
explicitly rather than silently bypassed to enable writes. Auto-generated forms
must be labeled as such. Archiving a configuration/module in SQLite does not prove
it can execute; opening a database or listing metadata must not execute its BSL.

## Native comparison boundary

Native 1C is a behavior oracle, not a reader of the SQLite database. Use official
XML configuration/form/module input and bounded BSL/text observations. The training
Docker edition permits one session: all native operations are strictly sequential,
with prior sessions reaped before the next starts. No binary database extraction,
native page/index analysis or native concurrency research is needed for this UI.

Choose an explicit measured platform/profile and bind observations to source,
module and official XML hashes. Record real outputs before implementing claimed
native semantics. A direct handler call is not an actual platform event or write
transaction. First useful discriminators:

- Form attributes vs client/server module variables, direct-name lookup,
  ThisObject, independent instances and close/reopen lifetime.
- Items/Commands identities, DataPath, visibility/availability/read-only state,
  server-side dynamic mutation and subsequent access restrictions.
- Creation/open ordering and cancellation; user input commit vs programmatic
  assignment vs direct OnChange invocation; command and cancellable close.
- Context-bearing server calls synchronize form data; NoContext cannot access
  it. Preserve ordinary argument transfer separately from UI serialization.
- Caught/escaping errors, repeated/stale events, closed controls and asynchronous
  work. Do not invent handler rollback rules from host navigation atomicity.

Object references/FormData conversion and the complete object-write event pipeline
need separate bounded measurements. Runtime DTO tests or SQLite durability tests
alone do not establish native event parity. See the official
[Developer Guide, chapters 7.7–7.9](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293).

## Integration gates

Test typed scalar/reference fidelity, identity/schema scope, source-independent
configuration/code reopen, bounded navigation, closed sessions, missing records,
unsupported profiles, wrong revisions and failure-without-success. Writer gates
add atomic rollback/conflict, interrupted commit/recovery and actual UI save/reopen.
Mocks establish routing, not durability. Process interruption tests are not a
universal power-loss proof.

Core track owns BSL/forms and official XML admission; database track owns the
logical service and SQLite transactions; UI track owns protocol/rendering and
the integrated user flow. Recompute exact runtime provenance on the composed
source and run the existing independent-review/CI gates. Do not reuse native
behavior evidence for a different runtime bundle. Other engines, full Query/СКД,
documents/register writes and multiple renderers must not block this first slice.
