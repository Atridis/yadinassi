# Owned form-result native acquisition (prepared, unmeasured)

This is a separate closed acquisition route for five **real native managed-form
lifecycles**. The historical one-form programmatic oracle and its 40 records are
unchanged. No result from this new route has been acquired yet.

## What the packet does

An owned external data processor has exactly two registered managed forms and an
inert object module. Main's real OnOpen starts a finite idle-driven chain. It
calls native OpenForm with an explicit owner and CallbackDescription. Child's
real OnOpen schedules its exported close action; the action calls native Close.
BeforeClose and OnClose are invoked only by the native form lifecycle, never by
the observer directly. Completion is invoked only through the descriptor passed
to OpenForm. The completion routine does not open or close another form.

Five flows observe:

1. A string result, event order, callback count and captured AdditionalParameters.
2. Close without a result, observing the resulting value kind.
3. A flat Structure result containing a fixed string and number.
4. First BeforeClose refusal, followed by a scheduled second accepted Close.
5. Cancel in OnOpen. Zero or one completion is recorded, including its result
   kind. Absence is only an observation over **three idle turns**, not proof that
   a callback can never occur later.

Each completion mutates the captured Structure. Main records its own Seen value,
so the observation distinguishes retained additional-parameter identity from a
copy. Result types/values and event order are measured, not installed as assumed
native expected values. Incomplete normal flows, missing close-refusal evidence,
unknown event codes and duplicate completions fail admission.

## Fixed sources and bounds

The packet comprises exactly eight native source files: processor metadata and
object module, plus metadata/Form.xml/Module.bsl for Main and Child. Constants
bind each raw source hash and combined source/form identity. Generated modules
only substitute two fixed provenance literals. Designer builds the EPF, then
re-dumps it; the exact eight-file inventory, full canonical XML, form UUIDs,
registrations, QName bindings, events and both module sources must match before
ENTERPRISE may run. Only BOM/CRLF, root serializer versions 2.4/2.20 and event
ordering normalize. Other serialization differences fail closed and require
separately reviewed evidence, not an automatic fallback.

There are five flow records, at most 16 event codes per flow, and a private trace
cap of 64 events. Each flow has at most ten one-second idle checks. The outer
native operation has a 120-second process deadline; build and re-dump also have
separate bounded calls. Public output is capped at 8192 bytes and the marker at
16384 bytes. Only fixed event names, flow ordinals, finite result-kind labels and
0/1 flags are exported. Paths, nonce, private trace files, raw logs and raw error
messages are not output records. The fixed native wrapper uses only paths from
the exclusively created, read-back-verified request inside its owned root.

## Isolation and evidence

The separate host retains existing digest-pinned image, owner/repository/merge
binding, read-only/network-none container, nonroot UID, dropped capabilities,
no-new-privileges, resource limits, fresh infobase, process/session-bus census,
secure descriptor reads, private cleanup and artifact hash checks. The shell
selector is exact and exclusive; there is no arbitrary packet/module selector.
Existing native profiles, protected fixtures and output goldens are unchanged.

A successful acquisition means `native_measurement_accepted: true` only after
source witnesses, native completion, process quietness and both cleanup
boundaries pass. `runtime_parity_accepted` remains **false**, and comparison is
`not_evaluated`. The older manual FormSession replay is not reused: it cannot
prove owned application lifecycle parity.

## Unmeasured risks and limits

The first acquisition must establish that the fixed external-data-processor
form name resolves under `/Execute` and that the idle-driven open/close wiring
is accepted by this measured platform. A failure does not permit weakening
source or cleanup guards. This external-form observation is not proof that all
CommonForm/application source profiles, modal/window modes, uniqueness options,
owner shutdown semantics or asynchronous completion handlers match native 1C.
The UI host's explicit owner-close refusal remains a host safety boundary.
