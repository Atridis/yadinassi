# Metadata-derived Catalog Description: bounded raw and typed reads

The read-only `read_catalog_binding` and `read_catalog_rows` APIs retain the
String Code, two primitive attributes, one active row/no freed row profile.
`DescriptionLength == 0` retains the original exact seven fields and offsets.
Positive DescriptionLength inserts one `_DESCRIPTION` NVC field after Code;
its declared capacity comes from CONFIG, and physical width is `2 + 2 * length`.
Binding reconstruction checks exact type, capacity, order, offsets, record size,
and neighbors before decoding. Existing string/record/lifetime limits apply;
there is no runtime allowlist of lengths8/17. Used UTF-16LE is strict, the prefix
counts UTF-16 units, supplementary characters use two units, and trailing spaces
are preserved. Unused capacity is not decoded. Typed UUID projection validates
the same owned binding/row without a second physical read.

## What has actually been measured

PR152 commit a318b990, native run40971133699, measured Description8/17 with
Payload32: widths18/36, ordinal5, offset56, record sizes145/163. Both created
full-capacity supplementary strings and shorter updates matched actual committed
readback, including trailing spaces. This establishes those two observations,
not every positive length, platform, or file format. The metadata-derived width
formula above is an explicit structural generalization. Description with
Payload64 was **not** observed by that historical run.

## Separate runtime acceptance lane

`catalog-description-rows-v1` uses invocation28, report53, capture54, aggregate55.
Its closed42-source inventory replaces the old measurement policy with the new
rows policy and adds the existing UUID codec needed by the public typed reader.
Old report50/schema2 measurement behavior remains a separate observational lane.
Shared source edits change old lane source hashes: historical receipts do not
validate this candidate's new runtime/source bytes.

The existing two credential jobs run separate Description8/17 cases. Each has
baseline/created/updated/applied states, with no new lifecycle stage or native
launch. Applied reuses the existing apply_cf observer session, designer2 and
runtime2, and requires Payload64. Its private schema3 witness contains actual
Description and canonical nonzero native UUID from the same fresh selection.
Baseline explicitly witnesses absence. Every present observer postimage is
quiesced, frozen, hash-bound and independently read once by the public typed API.
Only catalog name is a selector; witness values are compared afterward.

Successful new-lane acceptance requires Description, metadata and typed UUID
parity for all three present states. Differences/unresolved layouts fail closed
and discard the capture; old measurement verdicts are not tightened implicitly.
Private sidecars/values/UUIDs remain private and are cleaned under existing gates.
Public output retains only finite verdicts, counts and hashes. Case8 handoff is
exact-file/no-follow, digest/run/attempt/source-bound before case17 credentials;
compact aggregate validates both complete final reports and exact raw hashes.

Independent rectangular serialized maxima (including newlines where applicable):
capture6984 <=8192; full42-source report with a complete8192-byte capture
reservation28565 <=32768; aggregate633 <=2048. No cap is raised. Full lifecycle,
source provenance, cleanup and failure context remain present.

Empty/overlength native assignment enforcement, BSL managers/writes, numeric
Code, hierarchy, references/unions and multiple rows remain outside this slice.
Fresh exact-head native acceptance, including applied Payload64, is pending;
synthetic tests are not native evidence.

### Historical activation attribution (not current integrity pins)

The original activation test recorded the following historical SHA256s. The
current-source test now pins the deliberately reviewed new bytes directly, with
LF/CRLF and drift/BOM/lone-CR negatives retained. Neither set substitutes for the
new exact-head native acceptance.

- `catalog_reader.py`: `d5d57bd1c2ea66ab3774a08e0f396a7874701654be433d218217e5492a94d2f8`
- `config_catalog_binding.py`: `f7e3239cdf8597e4377eff6ca01c8bbbec8f2d071bd6931dbc3f9e19fd3dab98`
- `config_catalog_records.py`: `29346abc74341186a6ddd54d111c6ec5e2fe651dfc9bf8e8e57446dfeba3ffb4`

## Failure-only diagnostic follow-up

Fresh dedicated run40978039802 on source4f492d2a failed case8 after the applied
snapshot reported designer2/runtime2/Payload64 and the ordinary logical row
readback. The new typed Description hook did not complete; case17 was skipped.
The valid failed report has no capture and all cleanup gates passed. Its generic
`unexpected_failure` does **not** identify a layout, decoder, UUID or metadata
cause. No compatibility inference is made from the ordinary native lane.

The diagnostic follow-up preserves production readers, BSL and all parity gates.
A private exception is classified only after the same frozen descriptor's final
integrity/quiescence checks and exact postimage digest binding. An internal unique
sentinel permits those checks to finish; it never turns a reader exception into
a successful result. Superseding integrity failures cannot publish a reader code.
Only exact recognized classes and the existing finite diagnostic domain are
mapped; subclass, unknown and forged codes become fixed `unclassified` without
formatting the exception or reading user properties. Adapter and parity failures
have separate finite labels. Values, UUIDs, paths and descriptors stay private.

Optional `description_failure` exists only on a failed report with null capture,
matching final snapshot/stage and verified cleanup. Host failures scrub it.
Successful reports never contain it. The independent full rectangular envelope
reserves an additional157 bytes (total28565), still within32768; capture6984 and
aggregate633 are unchanged. These diagnostics require a fresh reviewed native
run before attributing the actual migration failure to any particular reason.
