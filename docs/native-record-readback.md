# Owned v1 physical-row validation lane

This is a narrow experimental lane of the existing file-database oracle, not
query support or a general logical metadata mapper. The ordinary names-only
contract `exact_tables_ascii_fields_v1` is unchanged. The metadata-only lane
still reports declarations only; neither old schema admits row verdicts.
The source-bound v2 fixture run below is accepted for its six bounded reads.
That does not establish general file compatibility or certify arbitrary inputs.

## Explicit route and source boundary

`--record-reader-validation` alone selects invocation schema 3, report schema 6,
capture schema 7 and lane `owned_record_readback_v1`. It is mutually exclusive
with `--record-metadata-observation`; unknown, abbreviated, combined or malformed
arguments fail before external work. The workflow deliberately selects the new
flag, without changing triggers, permissions, runner, image or isolation flags.
The default and metadata routes remain separately executable with their original
20/21-file inventories and invocation/report schemas. The new route pins exactly
23 inputs: the existing 21 plus `yadinassi/storage/filedb_records.py` and
`scripts/native_1c_db_oracle/record_validation.py`. `inputs.ROW_SOURCE_FILES` is
the exact inventory; source digests, commit/tree, image, platform, actual platform
version, locale and timezone are bound as before. No BSL or golden source changes.

The row decoder uses only the standard library and the verified catalog sibling.
The isolated loader aliases the already verified catalog module into a private
synthetic package before loading records. This preserves exception/limit class
identity and never imports `yadinassi.__init__`, Interpreter or installed
packages. A focused subprocess test actually initializes the staged run under
`python -I -S -B` and checks those import and class-identity constraints.

Adding the reader changes the separate standard six-output harness's host runtime
inventory from 57 to 58 files: one added reader and one changed catalog source.
Its staged 24 inputs and bytes, six output names and provenance output are
unchanged. Native reports from the older 57-source runtime cannot establish
acceptance for the new runtime. Fresh standard provenance must bind all 58.

## Evidence and fixed admission

The reviewed metadata-only run 40181431793 binds same-row logical identities,
Payload/Amount metadata paths and complete physical declarations. It does not
prove row offsets, codecs or descriptor `format_item`. This lane pins seven
ordered roles and declaration facts:

| Role | Logical identity | Type, nullability, length, precision, case |
| --- | --- | --- |
| reference | Ссылка | B, 0, 16, 0, CS |
| version | ВерсияДанных | RV, 0, 0, 0, CS |
| deletion mark | ПометкаУдаления | L, 0, 0, 0, CS |
| predefined | ИмяПредопределенныхДанных | B, 0, 16, 0, CS |
| code | Код | NVC, 0, 2, 0, CI |
| payload | Payload | NVC, 0, 32, 0, CI |
| amount | Amount | N, 0, 9, 2, CS |

The root logical/metadata target is exactly `Справочник.NativeOracleItems`.
Only Payload and Amount have nonempty field metadata paths, respectively
`Справочник.NativeOracleItems.Реквизит.Payload` and
`Справочник.NativeOracleItems.Реквизит.Amount`. All measured type-text cells are
empty. The complete mapping must be one-to-one, with exact table spelling and
ASCII-only field normalization plus duplicate/collision rejection. Raw spellings
are retained. Physical names come from this fresh same-row projection, not
historical incidental `_Reference`/`_Fld` suffixes, row values or string search.
One mapping/profile is fixed before any row values are read and reused unchanged
for all six images. This does not admit arbitrary configurations.

Profile `owned_v1_rv16_nvc_bcd127_intzero_v1` fixes record lock string `"0"`,
stride 127, declaration-order offsets `(17,1,33,34,50,56,122)` and widths
`(16,16,1,16,6,66,5)`. The source-bound canonical profile hash includes the logical
roles, all declarations, layout, codecs, empty framing and format hypothesis.
These are deterministic experimental mechanics, not independently measured
offsets. The accepted run below validates their bounded fixture readback only.

The sole format admission is exact integer `0`, never string `"0"`. Its semantics
remain unknown. The pinned Tool1CD source skips that descriptor item and comments
that it contains zero without defining or validating a node type/domain:
[Table.cpp lines 188–190, commit d5e31816f4c9b11a445f73fc92d08803840ce599](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L188-L190).
Exact Table.cpp SHA-256:
`420c5df09444c0af5a9736ce2c0523a1f070e451d458cf5cb620cbc6d2dfdcff`.
This fact supports only a falsifiable restrictive hypothesis, not a proven format
version. No GPL/LGPL implementation is copied, translated or adapted. Other
primary format facts and narrower codec hypotheses are documented in
[file-db-experimental-records.md](file-db-experimental-records.md).

A mismatch emits only one finite discriminator: integer-nonzero, string-zero,
string-other, list or other. It never echoes an AST, descriptor or unknown value,
never searches alternative formats, and grants no native acceptance. The tiny
failure capture binds the source/run/stage through its enclosing report, but
omits per-read target and observer hash. It is therefore a run rejection, not an
image-specific format observation suitable for automatically changing admission.
Any changed admission requires separate source review and new source binding.

## Accepted source-bound fixture evidence

[Run 40184433888](https://github.com/Atridis/yadinassi/actions/runs/40184433888)
was independently audited and accepted at head
`2973444c4234477429b05eb52831173a4745578a`, tree
`1e8df805210555f69a5433bc89a2dc9b83448708`, with profile SHA-256
`d70941ed1b52696a483ec7672aedff116595f24b796ffb8df29036be8c357d71`.
Artifact `12595546687` is 4,913 ZIP bytes, SHA-256
`2f81ee9cc8263d9b8eb1501043b580688ccd989e7e854f74c6cc900bac569bf9`;
its 20,036-byte report has SHA-256
`a5740e333bd423e082a4b0014729a2fb2a4ef90dfb8227d4ce7de60b157db4c4`.

The source-bound producer proof covers six original/closed-observer-postimage
reads, v1 empty/create/update, counts and Code/Payload/Amount/DeletionMark only.
Both baseline images admitted `empty_zero_length`; both created and both updated
images admitted `reserved_and_active`. The reserved-only empty variant remains
synthetic-only. The four mapped values matched the fixed states below with the
same pinned profile, source inventory and fresh metadata mapping.

Raw database images are not retained/exported, so this is an audited producer
proof, not an independent replay of retained DB bytes. It establishes neither
v2/deletion/free-slot behavior nor reference/version semantics, arbitrary
configurations, queries or general compatibility. The reader module still returns
native acceptance `pending`: it cannot self-certify arbitrary files. Reuse of
this evidence requires all 23 native source pins to remain byte-identical;
changed native inputs require a fresh source-bound run and audit. Test/document
changes do not substitute for current OS and standard-runtime validation gates.

## Images, lifecycle and private comparison

The existing 13-stage lifecycle, 11 snapshots and native call order are preserved.
Only v1 `baseline`, `created` and `updated` get row validation. The existing later
configuration-v2, delete and restore stages still run unchanged but confer no
physical v2/deletion acceptance. There is no extra native query/delete experiment.

For each selected state, compare both the original frozen snapshot and the closed
postimage of its existing semantic-observer clone. Do not assume byte identity:
the native session may change opaque bytes. Each read uses one pinned descriptor
across pre/post full hashes, frozen directory/file checks, bounded reads and
quiescence checks, including error exits. A disabled callback cannot be reused.
Original and postimage sizes/hashes are checked against separate private bindings.

Baseline order remains freeze, semantic observer, metadata auditor. Its closed
observer postimage is held only until that already scheduled auditor supplies the
mapping. The transient copy is reserved against the unchanged 512 MiB live cap
before copying, removed immediately after comparison, and covered by owned raw
cleanup on every failure. Created/updated postimages are compared and removed
immediately. No live database is passed to the Python reader.

The fixed expected semantic states are count 0; then count 1 with
`K1 / alpha / 1.25 / false`; then count 1 with `K1 / beta / -2.50 / false`.
Actual immutable reader results are checked for exact string/bool/Decimal types,
Decimal scale 2, active count and admitted framing. Native observer values must
independently match the same lifecycle expectations. Nothing substitutes expected
values for decoded fields. Reference, version and predefined bytes remain opaque
and are not independently accepted by this lane.

Empty framing requires an existing, fully validated table-data header with logical
length zero, or a single reserved slot with marker 1. Missing `Files[0]` is
unsupported, not an empty-table fallback. Nonempty files must have exact stride
divisibility, reserved slot 0 marker 1 and later active slots marker 0. Other
nonreserved statuses are unsupported. This source-supported zero-length case
corrects the earlier reserved-only hypothesis; no failed-open fallback exists.
Physical free-slot and native deletion behavior remain outside this acceptance.

## Finite transport and cleanup gates

Only owned metadata/declarations, source/profile hashes, three bounded image/token
bindings, finite framings and verdicts may leave isolation. No row/descriptor/AST
bytes, raw references/version data, offsets dump or arbitrary type text is added.
The native metadata projection retains its existing caps and strict validators.
Success requires all three origin/postimage pairs, the same pinned mapping/layout,
the unchanged lifecycle and all four cleanup gates. Any later source, transport,
lifecycle or cleanup failure discards the capture and all success verdicts. A
finite failure survives final transport only when all cleanup gates are verified.

Executable complete-envelope proof:
`tests/test_native_1c_db_oracle_readback_budget.py`.
It charges all 13 stages, 11 snapshots, 3 artifacts, 5 maximum comparison objects,
all 23 source paths, optional failure context, four cleanup gates and final newline.
Conservative independent maxima may coexist even when no valid report can do so.

| Bound | Bytes | Existing cap |
| --- | ---: | ---: |
| Seven-field native projection | 1,998 | 6,144 |
| Seven-field physical projection | 1,293 | 4,096 |
| Complete success capture | 5,622 | 12,288 |
| Complete finite failure capture | 113 | 12,288 |
| Whole public report using the full capture allowance | 31,447 | 32,768 |
| Conditional private JSON writer model, not a proven native bound | 8,931 | 32,768 |

The conditional private marker model charges all 16 allowed fields, full 6,144-byte
projection, ASCII escapes, four-space indentation, CRLF, final CRLF and optional
UTF-8 BOM. The unchanged BSL writer uses default formatting parameters whose
maximum indentation/escaping has not been independently established. Thus 8,931
is conditional arithmetic, not a proven native-marker upper bound or retained
marker measurement. The authoritative 32,768-byte read cap fails closed for any
writer output, including output outside this model.
No extra raw-row marker is created. Public headroom is 1,321 bytes; no cap rises.
Separate standard-harness proofs account for 58 runtime inputs: tightest wire
8,043/8,192 and pretty-report 32,228/32,768 bytes.

Focused tests exercise independent constructed bytes through the real producer,
freezer, actual standard-library reader and strict report validator. Wrong decoded
values/count, wrong original/postimage binding, format mismatch, mapping changes,
source changes or any cleanup gate prevent the row verdict. Synthetic tests are
not native evidence. The limited native claim is exclusively the exact source-bound
run above; publication and subsequent changes remain subject to source review,
current validation gates and whole-artifact audit.
