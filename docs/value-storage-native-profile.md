# Fixed native ValueStorage profile

`value-storage-v1` is a permanent, separately named native regression profile for
the supported ValueStorage slice. Its only BSL source is
`integrational_tests/measurements/value_storage.bsl`, SHA-256
`08f35c3672b3f3436df451ad8f7a604e5db7729f3b42dbae645e1ac362d5ca23`.
It runs cases 01–17 and 19–27: **26 cases and one calibration record**, exactly
27 messages. Compression case 18 is absent from this source and remains
unsupported. The original 27-case source, output and provenance under
`tests/fixtures/value_storage/` remain byte-for-byte unchanged.

The fixed source is the historical source with only the case-18 branch removed,
the fixed loop skipping 18, and the introductory comment updated. A local test
checks that exact projection and replays the 26 historical output lines. This
is a historical regression check, **not a fresh native acquisition**. Neither
the synthetic transport tests nor a historical replay proves that the new
profile has run successfully on real 1C.

## Scope and acceptance

- Positive cases 01–17 and 23–27 cover scalars, ordinary/fixed containers,
  independent snapshots, two shared-child scenarios, one untyped table cell,
  nested storage and constructor/Get through Eval. All 22 must return `ok`
  without the wrong-type marker. The original numeric/string/Boolean/date and
  positive Eval controls also retain their exact success requirements.
- Negative cases 19, 20 and 22 must report `construct-error`; case 21 must report
  `get1-error`. These are the acquired failure phases for the four fixed invalid
  inputs, not proof of native error text or arbitrary invalid-input behavior.
- Setup, mutation, inspection and observer failures always reject acquisition.
  Matching native/runtime action failures on a positive case cannot pass.
- Other positive values, such as the mutation/sharing encodings, are measured
  rather than prescribed by the wire validator. Fresh native output is compared
  byte-for-byte with an independent interpreter execution. A valid available
  observation can therefore be acquired while runtime parity is rejected.
  No filtering, normalization, substitution or partial comparison is accepted.

The finite per-case grammar preserves original case numbers and rejects missing,
duplicate, reordered or additional records, non-ASCII data, CRLF, missing final
LF and oversized output. Each record is at most 31 bytes; the rectangular bound
is 823 bytes including calibration. Existing runner limits remain unchanged:
8192 bytes for observation and stage report, 32768 bytes for public/provenance
reports, and 65536 bytes for transport. Closed diagnostics contain only the
server/client site and `record_count` or `api_controls`, with no raw failure text.

## Independent routing and evidence

The profile has its own registry identity, `--value-storage-suite` container
route, wire/stage schemas, contract and artifact names. Exactly 22 public source
inputs are staged. The managed-client adapter moves the single `VSPhase` module
variable before procedures, adds its client directive and captures the original
helper messages. Source pinning and an exact inverse guard the transformation;
it does not replace any ValueStorage action or expected native answer.

Both native contexts must complete with the expected nonce, source/module hashes,
client roundtrip identity, entry/completion witnesses, process exit, quietness and
process census. Their complete outputs must agree. Unavailable observations are
rejected at producer validation and again at host envelope validation, before
comparison or artifact export.

The existing workflow binds the admitted exact checkout and ordered merge
parents before credentials become available. Full repository, interpreter,
dependency and driver provenance is retained and rechecked after execution;
staged inputs, host sources and original Windows goldens are also rechecked.
The permanent profile does not freeze the whole interpreter to one historical
hash. Each candidate's complete runtime inventory must instead remain unchanged
during that run and be independently audited against that candidate.

For the source-only preparation based on PR200 head
`95197a4fb6eea6c7d7f1a975e5a82ee2d4315538`, the unchanged interpreter inventory has
116 files and aggregate SHA-256
`f64b2392fd26d9a303bcfc1ad8b97deb3ab9b4d3fb841a75c45fd3bb64b28a80`.
This is a preparation identity, not a permanent acceptance constant and not a
fresh runtime or native test result.

Format number/date sources, contracts, identities and observation counts are
unchanged. The ordinary six-scenario native suite is unchanged. The new matrix
row inherits the existing admission, isolated image, credentials, timeout,
cleanup and final-verdict gates; it does not introduce an alternate approval or
dispatch path.

## Execution after approval

Source preparation alone does not authorize a test or native run. Use the
repository's current light/Ready/heavy process; do not run a heavy partition or
an alternate full-suite command to bypass a Ready restriction. New tests are
unknown to the duration history and therefore remain in the light tier.

The fixed native command, only in an authorized clean, source-bound environment,
is:

```sh
python3 scripts/native_1c_tree_profile.py \
  --execute-approved-image --export-native-outputs --profile value-storage-v1
```

The source-only workspace is intentionally dirty and cannot satisfy the clean
checkout gate. The new CI matrix row is the normal native route, not a reason
to alter that gate. Its unchanged job limit is 60 minutes and isolated-container
limit is 2400 seconds; interpreter comparison has the existing 10-second limit.

Expected output locations:

- `native-1c-value-storage-summary`: `native-smoke/value-storage-report.json`.
- `native-1c-value-storage-outputs`: `value_storage.out` and `provenance.json`
  under `native-smoke/value-storage-outputs/`.

Before a compatibility/Ready decision, audit the exact candidate/run/attempt,
source hash, all 27 messages, native server/client equality, cleanup, unchanged
runtime provenance, `native_measurement_accepted=true`, and
`runtime_parity_accepted=true`. A successful acquisition with rejected runtime
parity is not sufficient. Heavy premerge coverage and all existing merge gates
remain separate obligations.
