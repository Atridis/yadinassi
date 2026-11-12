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
re-dumps it. The authored eight-file inventory remains closed. Redump reads only the three
known BSL files as bounded regular nonlinked files; XML output inventory is not
compared or read. A bounded tree scan rejects links, special files and unknown
non-XML payloads, including additional executable modules. Both form modules and the inert object module
must match normalized authored BSL (only BOM/CRLF normalization). Designer XML
serialization is not a prerequisite for behavioural acquisition: successful
Designer loading plus real lifecycle observations, rather than XML spelling,
are the evidence sought. Authored source still receives exact hash and canonical
XML checks before and after execution. The exclusively built EPF is hashed after
build and securely reread immediately before and after ENTERPRISE. No executable
module repair or arbitrary packet loader is permitted.

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

### Behavioural acquisition boundary

The first attempt stopped before ENTERPRISE on a strict XML redump mismatch;
it produced no lifecycle evidence. That structural serializer equality guard
has been removed only for this new lane. No separate XML diagnostic run is
needed. This deliberately trusts Designer's serialization of the owned XML,
while retaining executable module/source/EPF integrity and all sandbox, timeout,
process census, marker and cleanup guards. It does not prove XML roundtrip
parity, runtime parity, or arbitrary third-party form safety. Historical native
routes and goldens remain unchanged.

The second attempt passed build and executable redump but timed out before any
verified entry marker. This is not successful lifecycle evidence. Static review
found unqualified owner module variables used only from client handlers, unlike
the existing explicit client-variable probe. Owner state now declares AtClient;
entry is emitted before trace setup, and startup exceptions terminate without
exporting error text. The next real acquisition completed all five flows successfully.


## Acquired behavior

[Run 43005235949](https://github.com/Atridis/yadinassi/actions/runs/43005235949)
on source tree `0c86a3ee2c2ccfebe5055a2d73fcc59c1c21f344` completed on
1C 8.3.27.1508. The checked 400-byte output has SHA-256
`286dfe1c79767b8f78955bdca1efce5d4ee3ba07d71fa4768d027637ff4fad84`.

- String, Undefined and Structure each reached completion once, with the expected
  value and shared AdditionalParameters mutation visible to the owner.
- The first BeforeClose refusal kept the child alive; the second accepted close
  delivered exactly one completion.
- CancelOnOpen produced no completion during the bounded three-idle-turn observation.
- Every accepted close recorded BeforeClose, OnClose, then completion in that order.

Entry, completion, executable/source witnesses, process exit and cleanup were
verified. These are five real lifecycle observations, not a broad runtime/native
parity claim or XML serializer equivalence. The historical oracle is unchanged.
