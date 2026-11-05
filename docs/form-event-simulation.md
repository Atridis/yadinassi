# Bounded direct form-handler simulation

`simulate_form_event` is an explicit local-only host API. It freshly validates
exact original source and all three metadata byte inputs against the caller's
identity binding on every call. Canonical paths are derived, not read. The caller
must authenticate storage; hashes and UUIDs alone are not authentication.
No public analysis/AST, external sink, receiver, backend, path or runtime object
is accepted. Only Code/Description strings, DeletionMark/Cancel booleans and one
of OnChange/BeforeWriteAtServer are accepted. Exact scalar checks and existing
catalog qualifiers reconstruct a fresh private receiver before execution.

The complete #221 source profile is mandatory, plus distinct handler names that
do not collide with its receiver, parameter, message and builtin symbols. Both
original bodies are validated; the selected original procedure is invoked on
its own logical side through the existing interpreter, without rewriting BSL,
executing module initialization, or crossing client/server marshalling. No
routine names are registered. There is no managed-form event dispatch.

Each call owns a fresh interpreter, private scalar receiver, 256-node execution
budget and a one-record message sink. Reachable functions are only СокрЛП and
СтрДлина; the only constructor is СообщениеПользователю. Builtin namespace fallback
is blocked. The closed source cannot reach DataKey, SetData, dynamic calls, SQL,
files, network or persistence. No constructor or bind_data behavior is expanded.
The exact #217 UserMessageRecord must contain only bounded Text/Field, with empty
DataPath and absent DataKey/TargetID. Messages become frozen scalar DTOs.

The result contains an immutable candidate snapshot, cancellation flag and tuple
of messages. Server cancellation does not adopt or roll back the candidate;
callers may discard it. Deletion-mark early return preserves the input candidate
and cancellation. A failure raises and returns no partial result or messages;
there are no callbacks to retry. Input scalars and any prior result are unchanged.
No DB Write, baseline adoption, transaction, real 1C run, native parity, importer
activation, FormSession integration or GUI navigation is provided or claimed.

The exact source inventory is 125: base 121, three dependency runtime modules,
and this one runner/draft-session module. Eighteen runner test methods cover original-body behavior,
closed admission/capabilities, isolation, bounds and failures. Synthetic fixtures
are separate from the original demo smoke; original demo bytes stay unchanged.

## Host-only draft session

`FormDraftSession` is the next bounded host building block for the demo's Code
and Description form. It is not wired into the renderer, `FormSession`, importer,
or `CatalogEditController`. The constructor takes the same exact source, binding,
three XML byte inputs and initial Code/Description/DeletionMark scalars as the
runner. It performs full admission and existing scalar qualifier validation,
but does not run either BSL handler. In particular, loading `" x "` does not
silently trim it or emit a message. Existing catalog assignment qualifiers still
apply, including string truncation and refusal of malformed/split surrogates.

The session owns one immutable `FormDraftSnapshot`:

- `revision`: local host input-event revision, initially zero;
- `baseline`: qualified initial scalar pairs, unchanged for the session lifetime;
- `values`: current edit-buffer scalar pairs, initially equal to `baseline`;
- `messages`: the latest accepted change's bounded immutable message tuple;
- `native_parity`: always false for results produced here.

The baseline is a caller-supplied initial image, not proof of a persisted record.
The host authenticates the selected database/configuration/catalog/form and
current generation before use. `binding` exposes only the frozen identity/hash
commitment; neither hashes nor UUIDs grant access. Captured source/XML inputs are
exact immutable bytes. Every event freshly checks all four hashes, identity,
metadata and both original handler bodies through `simulate_form_event`. There
is no cached public analysis/AST, live receiver, callback, path or backend input.
Changing an active owner/configuration requires a newly authenticated session;
this offline API cannot detect external storage changes itself.

`change_description(value, revision=expected)` is the only edit operation.
Code and DeletionMark cannot be changed through input. The expected revision must
be an exact `int` equal to the current revision; Booleans and subclasses are not
accepted. A fresh private receiver is constructed with the proposed exact string
and the retained Code/DeletionMark, then the original OnChange body runs. Only
after successful completion are the normalized scalar image and messages adopted
together with one revision increment. Even an equal-value accepted event advances
the revision. Old snapshots stay unchanged; a later successful change replaces,
rather than accumulates, prior messages. Rejection, execution failure, or message
validation failure preserves the complete prior snapshot, with no retry or
partial messages. Single-owner synchronous access is required; this is not a
thread-safe transaction service.

`prepare_save(revision=expected, cancel=False)` runs the original
BeforeWriteAtServer body on another fresh detached image. It returns a frozen
`FormSavePreparation(revision, candidate, cancel, messages)` with scalar-pair
candidate and no live receiver. The revision names the session buffer used to
prepare it, never the private receiver's BSL setter count. Preparation changes
neither revision, baseline, edit buffer nor its OnChange messages, on success,
refusal, early return or failure. Refusal therefore retains the user's edits.
An exact Boolean input cancellation is preserved by the original handler.
Repeated preparation reruns local validation only, with no database write,
adoption or persistence retry. A prior result remains an immutable historical
image after later edits; it is not an object identity, authorization, save token,
or an API for committing anything.

### Future connection to the existing controller

This slice deliberately adds no commit/adoption API and no separate uncertain
outcome state machine. A future reviewed integration must first check the
existing controller's `pending_refresh` and `pending_commit` states and service
those branches **without running form BSL or preparing another image**. Only an
ordinary new save intent may run preparation before object setters and Write.
Uncertain outcomes must resolve the controller's retained exact submitted intent;
never replay BSL, replace that intent, or recreate the catalog object as part of
resolution. Verified persistence and refresh/adoption remain the responsibility
of the existing controller, not of these informational draft results.

No original BSL is rewritten. There is no DataKey, dynamic execution, module
registration, configuration activation, form dispatch, native 1C evidence or
claimed parity. No scripts from the demo archive are needed for this slice.

The draft test module uses synthetic admitted source. It covers detached change
normalization and messages, stale/exact revisions, read-only Code, hostile inputs,
immutable snapshots, fresh byte/identity admission, failed partial execution,
bounded message failures, refusal/candidate isolation and repeated preparation.
Run it and the existing runner/admission/scalar suites normally and under
`python -O`, then the relevant form/controller and scalar qualifier regressions,
after source review and pre-test notification. Source inventory remains 125 and
all existing execution, message, source and provenance caps remain unchanged.

## Verified inert-storage consumer

`VerifiedFormDraftSession(backend, catalog_id, code=..., description=...,
deletion_mark=False)` is a host-only consumer of the frozen
`SQLiteCatalogBackend.read_form_source` boundary. The backend must be the exact
host-owned SQLite backend, and the catalog must be an exact nonzero UUID. The
consumer requests only the declared `DefaultObjectForm`; it has no form/path
selector and accepts no caller source, binding, DTO, analysis, AST, handler,
callback or receiver. Initial Code/Description/DeletionMark are host-provided
scalars, not evidence of a persisted catalog record. Inert version 5 has no
runtime read/write capability, even when its archive can be opened read/write.

The returned source record and identity have exact frozen DTO types. The consumer
checks the database/catalog identity, canonical paths and same-owner default,
then derives the binding and four SHA-256 values from the returned original
module and XML bytes. It uses the unchanged complete admission/runner profile.
Absent or empty modules cannot pass. The storage reader has already validated
Configuration.xml ownership and the complete retained-file manifest within one
SQLite snapshot, closing the connection before returning. DTO type checks,
hashes and UUIDs are consistency checks, not authentication of a malicious
Python host. The host boundary must remain trusted.

`snapshot()`, `change_description(value, revision=...)` and
`prepare_save(revision=..., cancel=False)` retain the draft snapshot/preparation
shapes above; the original `FormDraftSession` public API remains unchanged.
`stale` exposes only a Boolean source-invalidation status. No public source,
binding, database object, identity/authority token or live receiver is exposed
to a renderer, and no renderer or controller is connected in this slice.

Each edit or preparation follows this order:

1. Reject an inexact/stale local revision and inexact input scalar types before
   any source read or execution. A previously invalidated consumer also refuses.
2. Read the source with the entire originally pinned identity as `expected` and
   check the full returned record against the original. Close the read snapshot.
3. Run the original BSL on a detached receiver and compute a detached candidate.
   The live draft has not changed, even temporarily.
4. Repeat the same source check after execution, with no transaction spanning
   the BSL interval. Recheck the local revision before returning/adopting.
5. Only a successful Description change replaces the single immutable live
   snapshot and advances the local revision once. Save preparation returns an
   informational detached result without adopting any state.

`schema_changed` from either check permanently marks this consumer stale and
read-only while preserving the exact prior snapshot, including dirty values,
client messages, baseline and revision. Restoring the previous database bytes
or swapping in a reopened backend does not reactivate it. The host must decide
explicitly how to preserve/discard edits and open a new consumer; there is no
implicit reload, rebind or retry. Other storage/admission/execution failures
return no candidate and adopt nothing. They do not grant write permission.
Server refusal retains the edit buffer and its prior client messages; server
messages belong only to the returned preparation. Repeated preparation stays
pure and creates no commit token or persistence API.

The last source read is only an observation of its snapshot, not a permit for a
later write. Storage can change immediately after it returns. Any future actual
write must independently compare the same database/configuration generation and
required source identity inside its own transaction. Before any future save
preparation, the existing `CatalogEditController.pending_refresh` and
`pending_commit` recovery branches must take precedence. Never replay BSL,
allocate a replacement catalog object, substitute current edits for retained
intent, discard an uncertain receipt, or unlock editing until the original
outcome is resolved. This consumer deliberately does not implement or wire that
recovery engine and does not grant DBWrite for any storage version.

The synthetic consumer test module covers read-only opening, exact original
bytes, closed inputs, detached adoption, immutable results, source/identity/hash
mismatches, generation and full-manifest drift, interrupted/transient reads,
failures after private mutation, sticky invalidation after restoration, and
connection closure before BSL. It also guards against activation, runtime reads,
writes, module registration and client/server marshalling. These are local host
tests, not native 1C parity or demo end-to-end evidence. No original demo BSL or
bundled archive script is changed or required. Runtime source inventory remains
exactly 125 (116 package files plus nine project/native inventory files); no
source/provenance cap is relaxed.
