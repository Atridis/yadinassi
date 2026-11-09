# Replicated form host API

`yadinassi.form_replication` is an opt-in Python embedding API for a detached
client/server form pair. It is not a new CLI mode, network listener or native 1C
compatibility claim. Existing `FormSession` remains a local shared-model session.
The synthetic tests do not replace native platform observations.

## Host ownership

Create `ReplicatedFormServer(server_source, endpoints, handlers=..., attributes=...,
tables=..., initial_values=..., bindings=...)` on the server. `endpoints` maps opaque positive
integers to contextful server routines with required `Val` parameters. Lifecycle
`bindings` select the server-create handler and client lifecycle handlers.
`handlers` is a tuple of trusted `InvocationBinding` procedure signatures
(`is_function=False`) for client handlers. The server installs empty client
signatures to validate composition and actions; it never receives client bodies.
An optional database context stays server-side.

Create `ReplicatedFormSession(client_source, exchange, handlers=..., bindings=...)`
on the client. Here `bindings` contains trusted contextful server signatures and
opaque endpoint numbers, not server source. The client source contains only
client routines and variables. The host supplies `exchange(bytes) -> bytes`,
usually the server's `exchange` method for local use or a separately owned
process/transport adapter. The two sides do not share form objects or controls.
The wire carries bounded scalar data, never source code, pickle, Python handles,
database connections or transactions. Endpoint and handler registration is host
setup, never renderer input.

## Lifecycle and synchronization

- `open()` bootstraps the complete bounded scalar schema, composition and action
  bindings created on the server, then runs the client open handler.
- `dispatch(event, revision=..., control=..., value=...)` uses the existing
  FormSession event vocabulary and stale-renderer revision check.
- Field edits and client appearance changes remain local until a contextful call.
  Before that call, the client sends its dirty values and appearance changes
  alongside explicit scalar arguments. The server admits the delta before
  running the trusted endpoint.
- The response supplies the full server form state. The client applies it before
  dependent BSL resumes, so the next expression sees updated attributes and
  controls, not just the returned scalar value.
- `snapshot()` returns detached display data; `messages` exposes collected output.
  A successful local close flushes pending state and closes the server form.
  UI revision, `server_revision`, `client_sequence`, request ID and backend record
  revision are distinct. Local edits do not imply a server round trip.
- `bind_nocontext(port, binding)` before open installs an ordinary scalar
  `InvocationPort` endpoint. Only explicit arguments/results cross that port;
  it does not flush pending form changes or synchronize form state.

## Failure contract

A completed server mutation is not rolled back when the handler subsequently
raises. A valid server-error response synchronizes those completed form changes
before a finite, catchable `server_error` reaches client BSL. Private exception
text is not a response payload. Backend transaction policy remains the backend's
responsibility, not a form-wire guarantee.

Malformed or lost responses leave the remote outcome unknown and lock the
session's `uncertain` flag. Later calls do not dispatch again. No automatic retry,
reconnect, reset, exactly-once database write or rollback is promised. The host
must reconcile uncertain server effects before starting a new session. Transport
security, authentication, timeouts and process ownership belong to the host.

An ordinary client OnOpen failure with a known remote outcome triggers a
best-effort `dispose` request, preserving the original exception. Cleanup drops
unsent client edits and runs no close callbacks. An unknown outcome never sends
this automatic cleanup. The host may also call `client.dispose()` for teardown,
including after a known local close-handler failure. It skips BSL callbacks and
dirty-state flush; an uncertain channel refuses disposal without dispatching.
The host must reconcile or tear down that server through its own transport owner.

Wire composition includes numeric creation identities for items and commands.
An existing local field reference remains valid across a barrier only when its
name, type and creation identity still match. Deleting and recreating a same-name
control invalidates the old reference instead of redirecting it to the replacement.

This bounded prototype does not establish native automatic-event ordering,
catalog-reference replication, arbitrary nested form values, remote module caching,
WebSocket support or native managed-form parity. No native integration scenarios
are changed by this host API.

## Bounds and current scope

The scalar boundary uses the existing exact InvocationPort codec: strings,
Decimal, Boolean, Undefined, Null and admitted interior whole-second Dates.
Form attributes also obey their scalar TypeDescription and qualifier contracts.
A Date attribute must therefore have an admitted value before its first packet;
the boundary does not silently widen native Date transfer support. Arrays,
structures, references and non-Val endpoint parameters remain out of scope.

Frames are bounded to 131,072 bytes and individual scalar strings to 8,192 UTF-8
bytes. The existing form limits still apply: 128 attributes/items, 64 commands,
1,024 allocated dynamic objects, 100,000 AST visits per event. The transport
admits at most 4,096 requests per pair. An entire input delta is validated before
any server mutation; an entire response is validated before any client mutation.
Rejected deltas do not consume the accepted client sequence or server revision.
Requests still have monotonically increasing identities and are never replayed.

## Fixed table replication

The private pair protocol is `yadinassi-form/1`. Trusted host registration supplies
`FormTableSchema` objects; the browser cannot define columns. Tables carry bounded
scalar cells, monotonic row identities and per-control selection. Client barriers
send existing-cell and selection deltas. Only server BSL can add/delete rows.
Detached admission validates the entire scalar/cell/selection candidate before
installation, preserves surviving row objects and invalidates removed rows.
An initially empty table schema inventory is also fixed after bootstrap.

The [table guide](form-tables.md) documents the limits, package manifest, browser
editing and durable create-only order example. Form collection/row handles cannot
cross an ordinary InvocationPort or serialization boundary. Known errors retain
completed effects; unknown outcomes remain locked without replay.

## Historical scalar verification

The dedicated `tests/test_form_replication.py` contains 30 scenario tests,
including a persistent separate Python server process. They exercise bootstrap,
dynamic composition, dirty changes, returned values, held/replaced controls,
NoContext isolation, lifecycle cancellation/disposal, failure synchronization,
malformed frames, replay, stale revisions and unknown outcomes. The saved
NoContext form adapter adds 15 tests in `tests/test_form_invocation.py`.

The original scalar milestone used the following 245-test regression set normally
and with `python -O`; this historical result is not evidence for later table changes. Tests execute real interpreter/transport code; native-runtime
harness tests in this command use their existing offline fixtures.

```sh
PYTHONPATH=tests:scripts python -m unittest \
  test_form_replication test_form_invocation test_invocation_port test_form_runtime \
  test_execution_directives test_nocontext_runtime test_nocontext_async_runtime \
  test_scalar_context_copyback test_execution_context_date_null \
  test_ui_asset_provenance test_native_preprocessor_budget \
  test_native_preprocessor_runtime_budget test_catalog_batch_receipts \
  test_native_preprocessor_runtime -v
```

That original production module increased the strict runtime inventory from 128 to 129
files; its three current expectation helpers are updated without changing the
inventory validator or its bounds. Browser assets and native integration sources
are unchanged. No browser test, new real-1C capture, complete repository suite,
packaging run or hosted CI verdict is claimed by this local result.
