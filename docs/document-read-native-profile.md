# Owned Document read experiment (runtime parity pending)

This next block prepares readonly Documents manager/reference/selection behavior:
Number, Date, Posted, DeletionMark, mixed scalar attributes and a Catalog reference,
default chronology, date ranges and FindByNumber. Two independently saved identity
sets reverse attribute declarations; each observes empty/three-row states in client
and server, four bounded blocks per session. Fresh UUID wires are retained exactly;
only their relational properties are compared across independent executions.

`document-read-v1` specializes the existing reviewed file-DB job, permissions and
source/ref admission. Twelve setup/observation sessions and two separate admin
audits reuse its clone/freeze/authentication/cleanup lifecycle. No caller script,
database path, credentials, global rights or new trigger is admitted.

The disposable generated Document alone receives Read/Insert/Update/Posting in the
existing CRUD role. Posting=Allow, RealTimePosting=Deny, empty modules, register and
sequence declarations, and false privileged flags are exact source invariants.
Only owned row 30 is posted; two others are ordinary writes. No Delete, Interactive
or UndoPosting grant is added. Public runtime remains readonly; the completed bounded implementation is described
in [Document runtime](document-read-runtime.md). Its actual `.1CD` parity gate is pending.

The saved XML is schema-backed and corrected from the first owned native redump;
the corrected two-identity batch is native accepted by run `41256261065`. Complete
semantic used-QName/tree equality remains required; no defaults are stripped.
On failure, only the two UUID+Name+kind-verified synthetic redumps may be captured,
up to 64 KiB each, with exact bytes/hash/identity/tag bounds. No private logs or
other metadata are exported. Their measured native defaults can correct inputs
without guessing optional values.

Raw observation retains CONFIG root/root-target and UUID-selected Document/Catalog
payloads, plus the per-run root-declared `NativeOracleItems` baseline descriptor,
selected DBNames and bounded physical declarations/data. The baseline must be the
sole additional Catalog reference and match its exact known identity/schema; its
UUID is never a routing constant. A DBNames
Document id → `_Document<id>` name is an explicit measurement hypothesis only;
unknown kind or absent table remains unresolved while native observations survive.
The observer itself does not infer Document membership, stride or field offsets.
The separate production reader admits only the CONFIG and all-active physical
profile established by the successful measurement; unsupported profiles stay closed. Cross-reader claimed
pages are checked against CONFIG/PARAMS and the other target before payload reads.

Completed native runtime `.1CD` parity and full/platform acceptance are pending.
Historical replay uses captured owned CONFIG/rows with an explicitly synthetic
auxiliary baseline descriptor; the final batch captures that fifth actual descriptor
and exercises the real frozen `.1CD`, not synthetic transport. `!todo` Broader Document metadata profiles, arbitrary table
parts, reference unions and unmeasured storage layouts remain closed until measured.

## Primary-source preparation

Schema/API evidence was extracted from official EDT packages (archives remain
local and are not shipped):

- [8.3.27 platform plugin](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform_v8.3.27_1.0.400.v202609220822.jar),
  SHA256 `4af9e1355b14b2836df4e89ae5d6c6e834d308e4233a490c12232e7dede67e4e`.
- [Platform documentation plugin](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar),
  SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.

`backend.xdto` declares Document (1970), DocumentProperties (2025), shared
GeneratedType (529), and zero-or-more StandardAttributeDescriptions (599).
The small source-derived schema profile is hash-pinned beside the packet.
DocumentManager (145) supplies EmptyRef/GetRef/Select/FindByNumber, not Metadata;
DocumentRef (147) supplies Metadata/UUID/IsEmpty and header fields; selection
(148) supplies Next, not Reset. Select (300) is chronological by default;
FindByNumber (299) distinguishes missing and empty numbers; GetRef (1618)
omitted/Undefined yields fresh references. Manager/selection availability is
server/thick/external, references additionally thin/web. Baseline controls and
late-bound expressions therefore measure actual context availability rather than
conflating an unavailable global with an observer compilation failure.

## First native redump correction

Run `41255615774`, source `48622aa3f257e339d193bf57dc5c849bbbca94f4`,
failed at exact fragment equality before setup, with zero observations and all four
cleanup proofs true. Its bounded report SHA256 is
`388c35d9d6dba1bedff803e480ff499d248f08bd86c13c84ee607e908115070c`.
The target Catalog redump was already semantically identical. The owned Document
retained all generated UUID/type and mixed-attribute identities, omitted five
nonserialized properties and catalog-only attribute `Use`, and supplied five
standard attribute descriptions (Posted, Ref, DeletionMark, Date, Number).

The generated input now includes those exact identity-independent standard
attribute defaults and omits only those measured absent nodes. This is not a
redump acceptance exception: the complete semantic equality guard is unchanged.
Date has FillChecking=ShowError; the other four have DontCheck. The original
failed report and exact owned redumps remain separately source-bound. At that
checkpoint, repeat two and actual CONFIG/physical/runtime parity were still pending;
the subsequent measurement below resolves acquisition, not runtime parity.

## Successful bounded measurement and remaining discriminator

Corrected source `d5a6284b6542f306002cf9cb7f86221d057b55b0` completed run
`41256261065`: both identities, two states, eight contexts and 32 available native
blocks; strict 159-source binding and all cleanup proofs passed. This is measurement
success, **not runtime parity** (Documents remains unregistered in that source).
Report SHA256: `a879485a6ae04dccc62e59faf84c41704a71a1c890578a1b48246769ed6331e0`.

Actual selection order is 20,30,10 by Date; exhaustion retains the last Number but
further Next remains false, unlike the measured Catalog restart. Exact equal
start/end timestamps include row30. Posted is true only for the setup-posted row.
`FindByNumber("") = Undefined` was false in both states, contrary to the initial
API-doc interpretation. Two formerly padded header slots now observe its type and
UUID in the final batch, without another session or invented expected value.
Historical replay must retain its original source-bound header program, not treat
old padding booleans as answers to these new probes. Fresh UUID bytes remain raw;
version-specific generation details are `!todo` and not a bitwise parity promise.
