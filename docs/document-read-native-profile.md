# Owned Document read experiment (measurement pending)

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
or UndoPosting grant is added. Public runtime remains readonly and unexpanded.

The saved XML is schema-backed, **not yet native apply/redump accepted**. Complete
semantic used-QName/tree equality remains required; no defaults are stripped.
On failure, only the two UUID+Name+kind-verified synthetic redumps may be captured,
up to 64 KiB each, with exact bytes/hash/identity/tag bounds. No private logs or
other metadata are exported. Their measured native defaults can correct inputs
without guessing optional values.

Raw observation retains CONFIG root/root-target and UUID-selected Document/Catalog
payloads, selected DBNames and bounded physical declarations/data. A DBNames
Document id → `_Document<id>` name is an explicit measurement hypothesis only;
unknown kind or absent table remains unresolved while native observations survive.
There is no assumed Document collection membership, stride, field offset or value
decoder. Existing production graph admission is unchanged. Cross-reader claimed
pages are checked against CONFIG/PARAMS and the other target before payload reads.

Completed native runtime `.1CD` parity, public Documents admission and full/platform
acceptance are pending. `!todo` Broader Document metadata profiles, arbitrary table
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
