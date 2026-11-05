# Bounded scalar FormData host contract

This is a local, non-native infrastructure profile, not a managed-form
implementation. `ScalarFormData` is only constructed by trusted Python hosts.
It is not a registered BSL constructor, importer target, FormSession attribute,
or renderer endpoint. No imported module is executed or activated here.

The host supplies a closed tuple of existing `FieldSchema` definitions, aliases,
and control bindings. Only exact immutable String and Boolean
values are accepted. Existing catalog assignment qualifiers apply; references,
numbers, dates, tables, nested paths, object methods, backend capabilities and arbitrary
host objects are rejected. Budgets: 128 fields/bindings, eight extra aliases per
field, 128-character names, 65,536 characters per string, 262,144 total characters.
Existing catalog UTF-16 qualifier/refusal policy also applies.

A binding maps one control to exactly `root.canonical-field`. The path is host
registration, never an evaluated expression. BSL aliases resolve only members.
Renderer read-only and member write permissions are distinct: the demo Code
control can be read-only without forbidding later trusted handler assignment.
Neither channel grants persistence. There is no UserMessage, SetData/bind_data,
data-key serialization or #217 transport integration in this slice.

Returned snapshots are immutable tuples of immutable values. Each patch validates every
member, type, qualifier and total budget before replacing the buffer once. A
failed patch changes neither values nor local revision. A failed later individual
setter does not undo earlier successful setters. The host owns single-threaded
access; revision checks are stale-input checks, not a concurrent transaction API.

`detached_save_image()` creates an independent receiver, with its own revision
starting at zero. A host may modify it during preparation, then discard it on
refusal or failure. No baseline, catalog object or caller buffer is mutated and
there is deliberately no implicit copyout, save callback, adoption or commit API.
This does not promise native handler rollback, database atomicity or cancellation
semantics. Persistence and any post-success adoption require separately reviewed
host orchestration and verified commit outcomes.

The separate host-only `FormDraftSession` in `form_event_simulation` now composes
this receiver with freshly admitted original demo-profile handlers. It can adopt
a successful detached Description change and prepare an informational save image,
without changing this scalar receiver contract or adding persistence. Its local
event revisions are independent of receiver setter revisions. See
[draft-session boundaries](form-event-simulation.md#host-only-draft-session).

Demo integration remains gated on admitted owner/source identity, controlled
handler execution, native evidence for required context/copy/refusal semantics,
message transport, and persistence orchestration. #221 static analysis is not an
execution capability and public fabricated analysis/IR must never unlock one.

Local test plan: 15 unittest methods covering aliases, capability rejection,
immutable snapshots, atomic patch validation/budgets, stale revisions, read-only
controls and members, detached save/refusal isolation, partial setter failure,
existing qualifiers, malformed values/Unicode, and closed schemas/paths. Run the
focused suite normally and under `python -O`, then form runtime and scalar
qualifier regression suites after source review and pre-test notification.
Native 1C execution is neither required nor claimed by these host-only tests.
