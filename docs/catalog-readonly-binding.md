> Current Description extension: see [metadata-derived raw/typed reads](catalog-description-rows.md).
> The Description0-only claims below describe the historical baseline and its receipts.

# Experimental single-Catalog read-only binding — accepted owned profile

The dedicated native lane is accepted for the bounded owned profile described
below. This is not a BSL Catalog manager, CRUD API, general metadata resolver,
or acceptance of arbitrary Catalog layouts.

## Independent compilation

`compile_catalog_binding(identity, attributes, dbnames, *, profile, budget,
limits=None)` receives the existing immutable CONFIG identity/attribute projections
and a completed DBNames parse. It never receives a physical descriptor, XML,
native metadata capture, expected values, or a database path. The explicit owned
profile admits String Code, no Description, and a complete two-attribute sequence:
variable String followed by signed Number. Names and UUIDs are not fixture constants.
Each selected UUID must have one unambiguous positive Reference/Fld ID; collisions
and incomplete collections fail. The table is `_Reference{id}`, attributes `_FLD{id}`.

CodeLength and attribute length/precision/scale come from CONFIG. The local finite
compile admission allows positive strings up to 2047 UTF-16 units and Number
precision up to 38 with scale between zero and precision, further restricted by
4096 bytes per whole record. These are conservative implementation ceilings, not
platform maxima or native coverage. Native evidence for this binder covers only the owned
Code2/Payload32/Number9,2 shape. Synthetic admission
of other qualifiers must not be represented as native acceptance.

## Measured fixed facts, not configuration constants

The old metadata-only [run40181431793](https://github.com/Atridis/yadinassi/actions/runs/40181431793)
(source `56e07ca0bb1862eed97efd5f1cede127e7f33965`, tree
`58d9cf8d7100688d0f05be34a91ade4c8330c119`) supplies a **prior owned-profile witness**
for the standard names/order and primitive declaration flags:

1. `_IDRREF`: B16, nonnullable, CS.
2. `_VERSION`: RV declared length0, nonnullable, CS.
3. `_MARKED`: L declared length0, nonnullable, CS.
4. `_PREDEFINEDID`: B16, nonnullable, CS.
5. `_CODE`: NVC, nonnullable, CI; length is separately read from CONFIG.
6. Complete CONFIG attributes in their admitted collection order, mapped by UUID.

The downloaded artifact12594414055 ZIP SHA256 is
`dc0605e9bed96960b5b3e754f8dcafc936c522a88818d95bdc066c9d59b7d925`.
Its18291-byte report SHA256 is
`abe1cee5d69a4721da82d4efa2f067c839ddda47d9c62956273b45f909d06651`.
All21 source hashes were checked against immutable Git blobs and the report passed
its exact-source FINAL validator. This authenticates the historical declaration
witness, not this new binder. Historical table/field numbers53/54/55 are **not**
compiled constants. No current native capture is an input to runtime binding.

Tool1CD at `d5e31816f4c9b11a445f73fc92d08803840ce599` independently documents
executable storage mechanics: FieldType.cpp gives RV16/L1/NVC(2+2*n)/Number((p+2)//2),
and Table.cpp418–438 places versions first, then remaining descriptor-order fields,
with leading status and minimum stride5. BinaryDecimalNumber.cpp separates a sign
nibble and decimal digits, with scale controlling fractional position. Its reader
ignores trailing padding for even precision and treats any nonzero sign as positive.
Our stricter sign0/1, digits0..9 and zero-padding rules are explicit local admission,
not a claim about every platform encoding. Upstream code is not copied or executed.

## One lifetime and unchanged legacy APIs

The private `_CatalogBindingGraph` consumes a previously completed CatalogReader
before any legacy table is opened. Exactly three ordered context-managed stages
cover the complete CONFIG parse, PARAMS extraction/parse/compile, and target record
read. All use the same source, page ownership and cumulative budget. No flags are
reset, no second reader is created, and no arbitrary physical page is accepted.
CONFIG/PARAMS require their data and BLOB; target records permit data only. Every
handle is identity-bound, single-use and revoked on stage exit. Mapping, parsing,
comparison, budget or late stage failures poison the lifetime; no retry/partial
success is returned by the intended coordinator.

The accepted original implementation below used a harness-only CONFIG transport
coordinator. The runtime extraction described next moves the live binding route
into storage modules without importing scripts. This remains an experimental,
caller-owned offline reader, not a BSL Catalog API. Public legacy `read_records`
and its fixed-profile admission remain unchanged.

`read_bound_catalog_records` validates its exact graph/reader/catalog identity and
independently reconstructs the entire binding layout before opening data. Frozen
but forged/replaced declarations, offsets, widths and stride are rejected. It
retains existing empty/reserved/active framing and rejects freed slots. Results
are private immutable physical rows; reference/version/predefined bytes remain
opaque. Decimal scale is derived from metadata and independent of Decimal context.

## Native acceptance and remaining scope

The fresh dedicated [run40824662535](https://github.com/Atridis/yadinassi/actions/runs/40824662535)
passed on its first attempt at original source
`cbbcd9a28d0f9eb2a43d2bb9b1cf13dfe153e2db`, tree
`7da0812a2dd09d1f796bee34fc229e95c3c25598` (696 source files, 35 staged files).
Its exact-source production FINAL validator ran cold before the unchanged,
independently prefrozen checker; both accepted the report. Six baseline/create/update
origin and observer readbacks matched independently derived bindings and row values.
Three Catalog metadata collections and two attributes were checked; all four cleanup
verdicts passed. This acceptance is attributed to that original source, not to later
documentation commits.

Artifact12876555108 ZIP SHA256:
`171397988c8bdf33e6ceb7dafd98331669dd74c52ba747ef5d7ff887be317ad7`.
The 19173-byte report SHA256 is
`c8f29c2bf42b1d60ac4f9eee47bb433b628eed4603904098b8d9efc8ab0c32f8`;
its public capture is 2434 bytes. Only the current owned String Code/Description0,
variable String and signed Number layout is covered; no altered-qualifier native
witness or general layout support is implied.

Separate original-source validation passed: 6087 local unit tests (one skip),
17 launcher tests, fresh Linux build/smoke, Move32 and Total32 binary replay on
six routes each, and a new whole138 runtime74 gate. The separate ordinary native
[run40824485588](https://github.com/Atridis/yadinassi/actions/runs/40824485588)
was also accepted for original `cbbcd9a28d0f9eb2a43d2bb9b1cf13dfe153e2db`;
it is not a substitute for the dedicated binding proof. Four-OS PR CI and later
merge/post-merge validation remain separate obligations.

CONFIG suffix/full grammar, hierarchy/owners/common fields, zero/unbounded or
fixed strings, references/unions, numeric Code, Description, extensions, applied
state resolution, deletion, indexes and live-database consistency remain unsupported.

## Dedicated producer implementation

The separate `--catalog-readonly-binding` route uses invocation23/report37/capture38
and exactly35 staged sources. `catalog_binding_reader.read_catalog_binding` is the
production harness entrypoint; its only selection input is `catalog_name`. It
creates one reader **per frozen image**, not one reader shared between different
images. All three roles for that image retain one budget and page ownership.

The unchanged owned lifecycle supplies six independent reads: baseline, created,
and updated origin images and each observer's closed postimage. Only after a full
CONFIG/DBNames/schema/row result exists does the policy compare canonical XML,
independent native/physical metadata and expected lifecycle values. Three Catalog
metadata collections are checked; only the original Catalog's current two-attribute
layout is a row witness. No rights, fixture metadata or native module changes are
introduced. No additional CRUD capability is exported.

The public capture retains source/profile/manifest hashes, audit bindings and three
paired-image states with distinct derived-binding and value verdicts. UUIDs, names,
qualifiers, descriptors and decoded row values remain private. The old record and
attribute lanes retain their closed protocols and original acceptance identities.

Local exact majorants: success capture2443 bytes, finite failure118, private marker
8931. The full report majorant including the **entire12288-byte capture ceiling**,
all optional diagnostic contexts and final newline is32688/32768. Only failed_stage
and failure_kind allowances use their exact production-enforced finite domains;
all seven other optional-context allowances remain128. Future enum growth changes
the executable bound. No cap was increased. These are local mathematical/report
construction checks, not native execution evidence. The separate source-bound
native acceptance above stays limited to the measured owned layout.


## Runtime coordinator extraction — accepted owned profile

`yadinassi.storage.catalog_reader.read_catalog_binding(read_at, file_size,
catalog_name=..., limits=None)` now coordinates the same three-stage lifetime
using only runtime storage imports. `read_at` is a bounded random-read callback;
the caller must supply a consistent, already-frozen offline image. The API does
not open a database path, acquire native locks, authenticate, or establish that a
live source is consistent. Its immutable result contains the private configuration
projection, selected identity/attributes, independently compiled binding, decoded
rows and cumulative usage.

`config_catalog_transport` contains the mechanically extracted live CONFIG
traversal, chain/inflate primitives and profile/observation dependency closure.
Its relative imports and direct attribute-projector import replace the harness's
flat staged imports; the parser logic, charges and admission are unchanged. The
historical source-pinned observer remains separate so old protocols and evidence
are not silently reinterpreted. The current binding adapter loads exact verified
runtime siblings and delegates; it contains no second live coordinator. Neither
XML/native capture nor expected values enter the runtime path.

The current restriction to String Code, no Description, two attributes and at most
one active record is intentionally unchanged. Code and attribute lengths and
numeric precision/scale still come from CONFIG. No arbitrary layout, multiple-row
selection, BSL manager/reference, applied-state resolution or CRUD is added by this
extraction. Those are subsequent independently measured tasks.

Synthetic tests compare every CONFIG result field, source callback and resource
counter against the historical implementation, including malformed bytes and each
lowered catalog budget. Separate tests exercise graph poisoning, late failures,
exact sibling loading and a cold storage-only read with no harness on the import
path. These synthetic checks remain separate from the dedicated native proof below.

The selected lane retains invocation23/report37/capture38 because its wire fields
and semantics are unchanged. Its exact inventory now contains37 sources, including
the two runtime modules; earlier35-source evidence is not acceptance of this source.
The complete report majorant is32137/32768, with the full12288-byte capture ceiling,
all lifecycle collections and final newline retained. All seven failure-context
fields now use the exact closed production-validated enum domains (including raw
metadata operation/phase values before mapping and allowed nulls), rather than an
unnecessarily loose128-character allowance. Tests cover each domain, JSON wire
length, rejection of out-of-domain/wrong-type values and growth of an enum. No
production report, capture or storage resource cap was increased.


### Source-bound runtime-extraction acceptance

The fresh dedicated [run40855667250](https://github.com/Atridis/yadinassi/actions/runs/40855667250)
passed on its first attempt at original source
`1a224d9369e6cad526bfe69a1d14a4d40c6d25e4`, tree
`a5ebb35a4ed893636118683f6552b68fc21473ad` (699 source files, 37 staged files).
Its exact-source production FINAL validator ran cold before the unchanged,
independently prefrozen checker; both accepted the report. Six baseline/create/update
origin and observer readbacks matched the independently derived bindings and values.
Three Catalogs and two attributes were checked, with 13 stages, 11 snapshots,
five comparisons, three artifacts and all four cleanup verdicts accepted.

Artifact12889186996 ZIP SHA256 (5167 bytes):
`6301c44cdcaffc7e29a0e8f76d2389d2d80a0e27be6563d6fa1c794142a3ae5e`.
The 19396-byte report SHA256 is
`f590c528ed507be224713e78dc34264e6054196144a9a158f6d3f45c31be1b2f`;
its public capture is 2434 bytes. This accepts the runtime extraction only for the
same bounded owned String Code/Description0/String+Number attribute layout. It
adds no BSL, CRUD or arbitrary database acceptance. The evidence belongs to the
original source above, not to later documentation commits; the earlier PR143
native evidence and its original-source identities remain separate.

Local validation of the extraction passed 104 focused tests, 17 launcher checks,
a fresh Linux build with the full production binary smoke, and a new genuine
whole138 runtime76 gate. The full unit process reached its 1800-second supervisor
limit after 5963 successful tests and one skip, without an observed test failure;
**that run did not pass the full suite**. The entire interrupted test module and
all remaining modules passed separately (131 supplemental tests), which is useful
coverage but not a replacement for a single full-suite pass. All recorded gates
retained unchanged source hashes, an empty owned process group and no leftover
fixture. Ordinary native CI and four-OS CI remain separate, pending audit
obligations before merge; this dedicated acceptance does not assert their success.

## Opt-in typed row UUID projection — native verification pending

`yadinassi.storage.catalog_reader.read_catalog_rows(read_at, file_size,
catalog_name=..., limits=None)` shares the existing private coordinator. Its
frozen `CatalogRowsReadResult` retains configuration observation, selected Catalog
metadata identity, attributes, binding, unchanged `PhysicalRecords`, typed `rows`
and cumulative usage. Each frozen `CatalogRow` contains `physical_record` (the
identical physical record, not a copy) and stdlib `UUID` `reference_uuid`.
Metadata identity belongs to the result; a UUID alone is not a Catalog identity
or a BSL reference. These private results must not be serialized into reports.

The new API admits the complete CONFIG → DBNames → compiled layout → physical
rows lifetime before projection. It decodes only the validated `_IDRREF` role;
`_VERSION`, `_PREDEFINEDID`, other binary fields and generic B16 decoding remain
opaque. No UUID is invented for empty baseline images. There is one reader, no
second source traversal, and no native expected UUID argument. Projection reserves
`512 + 512 * row_count` output units and `256 + 256 * row_count` processing units
on the same lifetime budget before validation/construction. These are conservative
accounting units, not exact Python allocator sizes. Any failure returns no result
and poisons the graph. `records.usage` still describes the unchanged physical-read
completion; the enclosing result's `usage` includes projection work.

The raw `read_catalog_binding` API does not import/call the UUID codec, acquire
projection charges, or change `PhysicalRecords`. The current one-active-row,
String Code, Description0 and two-primitive-attribute profile remains. Code width,
String width, numeric precision and scale are derived from CONFIG, not this API.
Nonzero Description is still rejected, rather than assigned a constant width.
No BSL manager, selection cursor, reference equality, database writes, live
snapshot admission, or broader schema support is introduced.

The standalone codec's accepted paired native run40918829096 (8 decode and
8 encode observations) resolves the earlier unknown UUID permutation, but does
**not** prove this new coordinator wiring. Native verification remains pending;
this development status is recorded here, not in typed result values.
Fresh paired native verification of this exact API/source is required before any
native-wiring claim, including independent runtime/native UUID comparison and
empty baseline/create/update origin/observer coverage. The present complete-image
synthetic tests are local wiring and rejection evidence only.

### Dedicated typed-row native verification profile — prepared, not yet accepted

The closed `catalog-reference-rows-v1` route has invocation26, report45,
capture46 and aggregate47. Its exact43-source inventory adds
`catalog_reference_rows.py` to the42-source codec inventory. The historical
identity and codec public validators retain their own exact inventories/schemas;
only the private fixed selector permits the new policy's structural codec view.
The workflow reuses the existing guarded codec A→B job pair and same-run,
same-attempt, digest/source-bound case-A handoff. It does not add native jobs,
rights, BSL modules or external database inputs. Its profile-distinct artifacts
are `rows_distinct_a.json`, `rows_distinct_b.json`, and `rows-aggregate.json`.
Only the exact rooted case-A artifact is ignored for source-cleanliness checks.

The staged adapter explicitly loads the codec into its otherwise pathless
exact-sibling package only for the typed route; raw binding reads remain unchanged.
Each frozen image invokes `read_catalog_rows` once, with no native expected UUID
argument and no raw reread. After image digest verification, the policy requires
the exact typed runtime result, exact UUID type, matching typed/physical counts,
and identical physical-record objects in order. It makes an internal raw view
sharing identity/binding/records for existing mapping/value/reference/codec checks.
Only then does it compare the typed UUID with the independently committed native
witness. Baseline requires both collections empty. No case-requested UUID is
substituted for the actual witness.

Each state records `projection` as `NN` for baseline or `TT` for live rows,
in origin/observer order, alongside existing `codec` `NNNN`/`TTTT` fields.
Both distinct-case reports are required: eight projected UUID comparisons plus
16 standalone codec direction comparisons. The aggregate retains only finite
verdicts/source/report hashes and fixed counts, not UUIDs or physical bytes.
All malformed/missing coverage, source changes, detached/reordered records,
wrong typed UUIDs, budget failures and unsuccessful cleanup fail closed.

The executable full-envelope bound is28788/32768 bytes, including the entire
8192-byte capture allowance and final newline; capture structure is bounded by
3545/8192 bytes. No report/capture cap was increased. Synthetic complete-image
lifecycle, actual staged cold import, seed/redump and real-Git handoff tests are
not native acceptance. A fresh exact-source paired native run remains required.
