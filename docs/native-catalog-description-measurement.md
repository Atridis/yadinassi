> This is the historical schema50 measurement design. Verified PR152 observations and
> the separate prospective runtime lane are documented in [Description rows](catalog-description-rows.md).

# Closed Description measurement lane (local integration; no native result)

This local integration extends no production admission. Native compatibility
and a real 1C run are **not claimed**. Its source baseline is Windows-fixed main
`69bd353b791393318aa30124f77e2a2a3acdf26b` (tree
`61e8b4b102c5654f7a1e1f0c62c08b296f6f56f6`). The earlier standalone seven-file
experiment is incorporated without loosening runtime Catalog bindings. Existing
42-source codec and 43-source typed-row profiles remain distinct and unchanged;
the new lane stages the entire 37-source binding closure plus four explicitly
listed measurement/policy/observer sources (41 total). No dependency is dropped
to shrink the budget. Exact source provenance pins every staged file.

## Closed cases

Use two separate fresh fixture databases, each with the existing single
`NativeOracleItems` Catalog and existing users/rights. Only DescriptionLength
changes: `description8` assigns length 8, `description17` assigns length 17.
Code remains String(2). Payload remains the existing variable String qualifier:
32 initially and 64 after the already-defined metadata migration. Amount remains
Number(9,2,Any). No extra Catalog, hierarchy, numeric Code, arbitrary schema,
manager API, live database reader or user database access is introduced.

The create assignments combine ASCII, Cyrillic, one supplementary scalar and two
trailing spaces at exactly 8/17 UTF-16 units. Update assigns a shorter mixed
string with one trailing space. These values are experiment inputs, NOT expected
native readback, valid-range claims, or runtime constants. Empty/overlength write
semantics are deferred. The observer permits unexpected bounded committed values
(including empty) rather than hiding truncation/normalization by a seed-equality
gate. No new lifecycle stage is defined. The private sidecar is produced at existing create/update/observe operations.
Create/update write after transaction commit and fresh selection; measurement
uses a NEW actual readback inside the corresponding observe session, never an
earlier write witness. Existing before/after logical checks remain intact.

## Source transforms and witness

`catalog_description_measurement.transform` takes exact original Catalog/server
template bytes, before existing literal substitution. Hash mismatch fails closed.
Only explicit anchors are replaced, with an exact byte inverse verified against
the original digest. The original templates and injector are not edited. The opt-in injector, promotion and redump validator now use these exact
transforms; unselected modes preserve historical universal-newline behavior.
Narrow `.gitattributes` LF rules preserve the pinned template/hook bytes on
Windows. Selected CRLF mutations still fail the byte hash; hashes are not
normalized to hide source changes.

`CatalogDescriptionObservation.bsl` performs a fresh selection, checks at most one active row with the saved reference, and writes schema2
`present` plus the actual Description string to a private sidecar. An absent
row requires empty value; a present row may also legitimately have an empty
Description. The baseline observer must be absent and is not submitted to the
one-active physical adapter; created/updated observers must be present. The host reads through the existing no-follow/regular-file boundary, validates
the main result/completion markers before retaining the witness, binds
nonce/token/case/observe-operation, and unlinks the sidecar even on error. The
exact observer clone is frozen after native quiescence, read on the hardened
frozen descriptor with pre/post hashes, then removed through existing cleanup.
Native readback and physical observation therefore bind the same session
postimage, with original snapshot digest retained as provenance. The decoder rejects unknown/duplicate keys, malformed UTF-8/UTF-16,
wrong types and identity mismatch. Maximum actual value is 128 UTF-16 units and
maximum sidecar 2048 bytes. These are transport ceilings, not native capacities.
The source inputs and native witness remain separate; native readback is never
used as a physical table/field selector.

## Independent physical measurement

The physical observer first admits the complete generic physical catalog, then
traverses CONFIG and PARAMS/DBNames and selected records in one existing lifetime
ownership graph with cumulative budgets. Catalog identity and qualifiers derive
from CONFIG; fixed experiment capacity is checked afterward by
`verify_case_metadata`, not passed into the byte reader.

The standalone closed layout hypothesis is the known seven-field Description0
shape, or that shape with one `_DESCRIPTION` NVC field following Code. Physical
width is derived from observed metadata and validated declaration, not the case.
Recordlock displacement retains the known Version-first storage convention.
Unsupported valid descriptors remain `layout_unresolved` measurements, not runtime
approval and not a search for a field whose bytes happen to match native values.
One active row, reserved header and no freed slots remain required for decoding.
A failed structural or budget admission is not a successful descriptor result.

Compare the independently decoded Description with actual committed native
readback only after physical admission. Record privately ordered declarations,
placements, record size, Description ordinal/type/width/offset, adjacent offsets,
raw used-unit prefix and strict decoded value. Public exposure is limited to
finite verdicts, counts and hashes. Native/Python scalar counts must not be
confused with UTF-16 units: a supplementary character supplies the discriminating
case. A shorter replacement tests stale tail handling; unused padding is not
interpreted as additional string content. Description0 control must preserve the
original seven-field offsets and decode, while production Description8/17
bindings continue to reject.

## Closed wire, bounds and publication gates

Fixed invocation schema27 selects only `description8` or `description17` under
`catalog-description-measurement-v1`, mutually exclusive with every old lane.
Report50/capture51/aggregate52 are separate from old report45/capture46 and
aggregate47. Case widths come from CONFIG and are checked against the fixed case
only after physical reading, never supplied as expected values to the reader.
The profile hash commits seeds and the observational hypothesis. Complete source
manifest and rendered metadata/redump equality authenticate the actual code.

Capture remains 8192 bytes; full report remains 32768 bytes. Independent finite
rectangular tests reserve 5154 bytes for the capture, 28304 for the complete
41-source report including the FULL 8192 capture allowance and newline, and 640
for the compact aggregate under its 2048 ceiling. These include core 13 stages,
11 snapshots, finite failure/context maxima, provenance and cleanup. Every
runtime serializer still enforces its actual hard cap. The private witness has
its own 2048-byte hard cap regardless of unmeasured native writer formatting.

Each case uses a separate invocation, nonce, artifact and bounded capture. The
old standalone 6364-byte raw planning subtotal was per case only; combining both
cases' four checkpoint payloads into an 8192 capture is forbidden. The aggregate
contains only case/outcome/report-hash/source-hash/run/attempt records and never
nests reports. Case17 requires the exact case8 filename, no-follow descriptor,
no extra artifacts, authenticated digest, same run/attempt/commit/tree/sources
and a separately validated final report before credentials are exposed.

The existing two credential jobs select the new closed route; package access,
container restrictions, checkout SHA and workflow admission gates remain intact.
Older routes remain selectable and their historical checks are not relabeled as
Description facts. Source publication and real native launch are separate gates:
this local candidate does not establish native support. A completed measurement
can report `readback_differs`, `layout_unresolved`, or `case_metadata_mismatch`;
its accepted flag attests lifecycle/evidence/cleanup completion, not compatibility.
Cleanup or transport failure discards the capture and cannot retain successful
measurement conclusions. All physical strings, descriptors and witness values
remain private; only bounded verdicts/counts/hash commitments are public.

Before publication: focused normal/-O tests, old-lane regressions, complete bounds,
source closure, independent review and immutable diff. Before runtime support:
source-bound native evidence, same-postimage readback comparisons, reviewed layout
facts and a separately scoped production change. Empty/overlength assignment
semantics and general BSL Catalog managers remain deferred.
