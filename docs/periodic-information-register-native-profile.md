# Second-periodic independent InformationRegister: closed native measurement

Prepared from main `12083d565752333cb641bd05c5d4740bfd45bd7f`.
This source adds a separate closed measurement lane, not public periodic register
admission. Existing nonperiodic InformationRegister reading remains unchanged.

## Intended readonly workflow

An independent register uses Second periodicity, Product (fixed CatalogRef) and
Variant (Number9.0) dimensions; Price (Number9.2), Available (Boolean), ValidUntil
(DateTime) resources and Note (String32). Two saved, distinct metadata identities
reverse declaration order. Totals, recorder mode, history, modules and external
calls are excluded. Public writes are not part of this work.

The prospective API block is GetFirst/GetLast for complete keys, SliceFirst/
SliceLast for empty or bounded dimension filters, and periodic Select with Date
range boundaries and the indexed Product filter. Boundary/PointInTime and other
periodicities remain outside scope. The local pinned official EDT documentation
establishes API signatures, not physical encoding or native results.

Five input rows deliberately mix insertion order, repeated keys across seconds,
and different keys at the same second. Empty and filled snapshots are observed
for both identities on client and server: four blocks of 24 observations in eight
readonly contexts. Setup uses only generated-owned fixture data and existing
scoped Register Read/Update plus Catalog preparation rights. Native Query
witnesses check all five inserted rows independently of the public read APIs.

## Evidence and security boundary

The existing reviewed-ref job, image, authentication, process confinement,
read budgets and cleanup contract are reused. The staged inventory omits only
the previous nonperiodic saved packet and its two replaced entrypoints; all
shared modules remain pinned. Cold isolated imports and complete installer tests
verify this closed dependency set within the unchanged invocation-byte cap. Whole used-QName XML equality
remains strict; bounded diagnostics can retain only identity-verified generated
Document-free register/Catalog XML. No arbitrary default stripping is allowed.

Same-root CONFIG capture includes root, root target, register, target catalog
and the exact verified per-run NativeOracleItems baseline. Selected DBNames
roles, actual declarations and bounded raw table bytes are evidence only.
Period storage, physical key order, liveness and any additional layout remain
unresolved until actual capture. No assumed seven-byte extension or synthetic
native expected output is admitted. Frozen postimage digests and quiescence are
checked around offline processing; source-integrity failures stay hard failures.

Original authenticated acquisition reports remain private. Any future public
regression fixture must include only the minimum source-owned CONFIG/rows/BSL/
observations and proof hashes, excluding installations, audits, sessions,
credentials and authentication tokens. Separate payload authorization and
platform procedures apply; previous individual XML/JSON permissions are not
silently extended to new files.

Actual Designer redump, logical API observations, periodic physical layout and
final offline `.1CD` parity are **pending**, not inferred from local synthetic
host tests. A successful measurement alone is not production admission.
