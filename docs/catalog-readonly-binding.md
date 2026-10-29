# Experimental single-Catalog read-only binding — local prototype

This prototype has synthetic evidence only. It is not a BSL Catalog manager,
CRUD API, general metadata resolver, or accepted native row-binding lane.

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
platform maxima or native coverage. Native evidence for the previous independent
pieces covered only the owned Code2/Payload32/Number9,2 shape. Synthetic admission
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

CONFIG transport orchestration is still a **harness-only private seam**. The pure
runtime compiler and bound-record reader do not import scripts. This prototype
therefore does not claim a standalone public offline Catalog API. Public legacy
`read_records` and its fixed-profile admission remain unchanged.

`read_bound_catalog_records` validates its exact graph/reader/catalog identity and
independently reconstructs the entire binding layout before opening data. Frozen
but forged/replaced declarations, offsets, widths and stride are rejected. It
retains existing empty/reserved/active framing and rejects freed slots. Results
are private immutable physical rows; reference/version/predefined bytes remain
opaque. Decimal scale is derived from metadata and independent of Decimal context.

## Required next evidence

A fresh dedicated source-bound lane must independently compare the complete
CONFIG identity/type collection, DBNames/physical mapping, and decoded baseline,
created and updated rows against the owned canonical XML/native lifecycle. Parser
inputs must remain expectation-free. Existing matrix fixtures and rights can be
reused for the current profile. No native acceptance, full-fixture pass or workflow activation is claimed here.
The implemented finite protocol and local budget proof are described below.
CONFIG suffix/full grammar, hierarchy/owners/common fields, zero/unbounded or
fixed strings, references/unions, numeric Code, Description, extensions, applied
state resolution, deletion, indexes and live-database consistency remain unsupported.

## Dedicated producer implementation (native run pending)

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
construction checks, not native execution evidence. Fresh full gates and a dedicated
source-bound native acceptance remain pending.
