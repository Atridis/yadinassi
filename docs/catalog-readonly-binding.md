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


## Runtime coordinator extraction (native validation pending)

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
path. These checks are not a replacement for a fresh dedicated native run.

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
