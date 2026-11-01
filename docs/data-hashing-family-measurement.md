# DataHashing ordinary workflow measurement

Status: **local packet only; native observations are pending**. Local execution
is not a platform golden. MD5 and SHA1 are covered for language compatibility,
not recommended for security-sensitive hashing, signatures, or password storage.

## Primary reference and execution context

Signatures were checked in the official EDT documentation archive, SHA-256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`:

- `nl/{en,ru}/html/SyntaxHelperContext/objects/catalog63/DataHashing`;
- `nl/{en,ru}/html/SyntaxHelperContext/objects/catalog2/catalog2088/HashFunction`.

`DataHashing` / `ХешированиеДанных` takes a `HashFunction` / `ХешФункция` value.
The five enum values are CRC32, MD5, SHA1, SHA256, SHA512. `HashSum` is a Number
for CRC32 and BinaryData for the other algorithms; `HashFunction` and `HashSum`
are read-only. Append accepts UTF-8 text, BinaryData, or a stream with optional
byte count. AppendFile consumes file bytes. HashSum observation must not reset
incremental state. SHA512 and the documented current HashSum form are available
since 8.3.18; the intended existing native target is 8.3.27.1508.

The docs list **server and thick client**, not thin/web availability. The existing
native harness declares `managed-thick-file`; verify that actual context in the
acquired provenance before reporting native coverage. Do not infer thin-client,
web-client, or browser support from this packet.

## Bound packet

- `integrational_tests/measurements/data_hashing_family.bsl`
- SHA-256 `0747e214310432fc0bc36af922d7443d15ff0c082bc9b8356403a7ca874b827d`
- 6,746 UTF-8 source bytes; additional packet bound 8,192 bytes.
- 40 cases plus 2 observer controls; 42 messages and 5 print sites.
- At most 40 UTF-16 units per successful case; exact output rectangle 7,130 bytes,
  below the unchanged 8,192-byte output cap.
- Two controls encode empty text and a string including a supplementary character.
  Ordered hex-unit framing rejects malformed, missing, duplicate, and oversized
  records. Action failure and observer failure are distinct finite labels.

The empty/`abc` vector witnesses compare **complete** digest values against fixed
public test constants, including all 64 bytes of SHA512. They emit the comparison and digest size; case 06 additionally emits the actual
CRC32 of `123456789` using ungrouped formatting to distinguish unsigned and signed
high-bit representations. These constants are ordinary algorithm test inputs,
not invented native output. Other rows compare complete digest values across
incremental/binary/stream/file workflows; raw long digests and paths are not
published. The wire contract validates shape and availability, not assumed
semantic answers or a cryptographic security property.

## Coverage

| Cases | Workflow |
|---|---|
| 01–05 | Empty input, each of five functions; full vector and result-kind/size witness |
| 06–10 | `abc`, each function, full vector witness; case 06 also emits actual CRC32 of `123456789` without grouping to observe high-bit signedness |
| 11–15 | `a` + `b` + `c` versus one append; repeated HashSum reads without reset |
| 16–20 | Empty and intermediate HashSum snapshots remain independent after appends |
| 21–24 | UTF-8 Cyrillic/accented/astral text, embedded zero/255 binary bytes, mixed text/BinaryData |
| 25–29 | Stream count omitted, partial, empty omitted-count, over-EOF/at-EOF, nonzero source position and resulting cursor |
| 30–31 | Fresh-instance state reset; borrowed read-only view/shared cursor remains usable |
| 32–35 | Property reads, repeated BinaryData Append, exact positive stream count, type/enum identity |
| 36–40 | Each algorithm: mixed prefix + owned AppendFile + suffix, owned deletion and post-deletion hash preservation |

The table above describes the retained ordinary source7a126ea8. The current
SHA512 discriminant replaces six slots as detailed below.

## Owned-file discipline

Every file case requests a fresh temporary root and rejects collision before
creation. Only the known child `a.bin` is created or deleted. The directory is
removed only when enumeration proves it empty. Unexpected children remain
untouched. Failures use the same restricted cleanup. Focused tests inject append
failure, a pre-existing root, and an unexpected sentinel child. No recursive
cleanup, user files, repository paths, permissions, network locations, credentials,
or raw exception text are involved.

## Integration recipe and evidence limits

The local checkpoint includes one closed shared registration (not yet published):
`data-hashing-family-v1`, case `data_hashing_family`, artifact
`data-hashing-family`, contract `native_1c_data_hashing_family_contract`, count 42,
print sites 5. The exact declaration/body marker is:

```
\nСообщить("HF-C1: ["+HFEncode("")+"]");\n
```

Source LF and future capture byte-preservation rules are included. The existing
reviewed native machinery, permissions, contexts, and bounded process/input/output/
cleanup gates remain unchanged; the local hooks select only this new closed profile.
Actual source/module hashes, native captures, context/cleanup evidence, and exact
parity must be audited before acceptance. Count-at-EOF, CRC32 unsigned behavior,
and lifecycle/error semantics remain measured questions until native acquisition.
`!todo` async, exotic streams, and rare large-input/platform corners are deferred.

## Initial acquisition and finite failure diagnosis

PR181 head `4e091797785287eddd1467f602ce6ba79115fa85`, native run
41322185475/job124894576191 rejected the producer result with `invalid_result`.
The validated summary ZIP digest is
`cb48f80c199621007869012cb822c958805e8d084dcb1d31be79dba24b5b4e7a`.
No raw40 output was exported; this does **not** prove that no observations ran,
that compilation failed, or that the family is unsupported. Other native lanes
passed. The original failure is retained; no runtime semantics were changed.

The next acquisition preserves the ordinary result parser and adds only a
failed-result diagnostic for this exact source-pinned profile. Categories are
`result_json`, `result_shape`, `result_error`, `result_encoding`, `result_limit`.
An optional line1..89 comes only from the literal generated TestModule object
module frame. Other module names, paths, raw errors and free-form text are never
exported. Secondary inspection is bounded to16KiB before decode; larger rejected
results emit only `result_limit`. The existing failed-only envelope requires no
outputs, incomplete native tests and failed stage/source identity. This is not an
acceptance fallback and does not change parser, payload, process or security caps.

The first diagnostic run41323358848 on `d150654` established `result_error`
with no matched owned line: the bounded result had a nonempty launcher error.
No raw observation was exported. Its summary ZIP SHA-256 is
`cf286038af9ab9053fca246b8ebdd4afdf3bd68441e4a0f740163c882383d361`.
The owned launcher uses DetailedErrorDescription. The next diagnostic admits
the same literal owned frame with an optional column, and only the closed kind
labels identifier/function/type/method/syntax/module/other from fixed phrases.
The existing calibration field carries that enum (or null for older witnesses);
this is a bounded hint, not raw error text or independent proof of the cause.
Failure-only admission and all source/resource guards are unchanged.

The second diagnostic (run41324060953, head74c9d39) returned `result_error`,
kind`other`, no owned line. Summary ZIP SHA-256
`9ba2f8538ec1340f8d6acf2185be04aa98db12438e0f9caafca20646d6c4b504`.
The actual cause remains unknown. Do not infer unsupported DataHashing APIs.

The next **local-only proposal, publication pending privacy review**, replaces
unhelpful free-form inspection with a pure allowlist projection: at most64 token
IDs, where0 means redacted, using only fixed public-source identifiers and fixed
error vocabulary. No dictionary entry is learned from a run. Unknown values,
quoted text, URI/path chunks and uncertain bracketed regions are redacted. A
single exact public-source identifier in parentheses may be represented by its
fixed ID. All emitted strings are schema/enum constants, never input text.
The exact phase witness contains only message count0..42(or null), exact observer
control1/control2 presence, and a case-record presence boolean; no raw messages.
The complete projection is less than1KiB and remains source-bound and failed-only.
Synthetic canary tests cover credentials/user/path/URI/quoted known identifiers,
unknown fields/types, all fixed bounds and attempted success/payload admission.

A later failed-only phase revision adds a 40-bit valid-case bitmap and an
ordered prefix length0..40 after the two exact controls. Gaps, duplicates,
out-of-order or malformed records cannot extend the prefix; no record content
is exported. This identifies a completion boundary, not the native error cause.

## Original zero-count workflow remains unavailable

The original source SHA-256 `237b2b7df6ec9a16c1e17956b4bfc57c3d8b3cf1826d695fecae1a9e288b6602`
is retained in Git history. Run41326610981/headad12fdc2 yielded both controls,
exact ordered valid records1..26 (bitmap67108863), and a nonempty launcher error;
no case27..40 record was exported. Summary ZIP SHA-256
`6a10b3ae66f2fa525d80e2102d64455b1daeaa698522430ad81f6725885054b1`.
This proves the completion boundary, not that explicit Count0 means no-op or
all-data, nor that the26 records passed. Original40 parity was never accepted.
!todo Explicit Count0 stream workflow is temporarily unsupported/catchably rejected;
it must not be re-run as an allegedly ordinary supported operation.
The revised packet keeps40 IDs but replaces slot27 with an empty stream and
omitted Count. All other cases and resource/cleanup guards are unchanged.

The next original-error boundary is also retained: revised source
`f43a6793a6ca4b3c0e3ba347c40559c0175fdd78f71069276601eb7e33a9c523`,
run41327349124/head8697f087, emitted exact ordered records1..29 and then a launcher
error before slot30 (closed-stream Append). Summary ZIP SHA-256
`051ab053b7be56eb32bccce4397661fe1c0a9deaf95ff23d334db97c40dd5ba3`.
This still provides no accepted raw40 or passed-record claim.
The ordinary packet now replaces30 with fresh-instance state reset and34 with
exact positive-count stream input. Closed-stream and negative-count rejection
remain local integrity guards, not measured native exception semantics.

This single revision also makes32/33/35 and36–40 strictly ordinary: property/type
reads, repeated valid BinaryData appends and owned file/hash observations replace
intentional property assignment, wrong-type construction/Append and missing-file
Append. Those error semantics are not native verified; local negative guards and
tests remain unchanged. This prevents serial execution of unmeasured rejection
paths while retaining all five algorithm/file workflows and cleanup checks.

## Ordinary capture and actual SHA512 representation discriminant

The previous ordinary source `7a126ea8f2dc1b94b9926b2a12d25554933c32fd7dbca7534ac84104c1027ab6`
produced40 available records. Its minimal public source/output fixture is retained
under `tests/fixtures/data_hashing_family/native-ordinary-v1`; only5/10 differed
from local replay (SHA512 empty/abc Base64 vector comparisons). Both literal known
vectors match standard SHA512; this does not yet distinguish hash bytes from
Base64 representation, e.g. possible line breaks.
The current40-slot packet observes actual SHA512 Base64 in three parts per input:
empty5/15/30 and abc10/20/33. Part1 contains length plus first32 characters;
part2 contains next32; part3 retains the complete remaining tail (bound40).
No whitespace is normalized, so any CR/LF remains in the UTF16 wire. Runtime hash
algorithms are unchanged. The previous ordinary coverage remains replay-tested.

Capture audit limitation: the original transport envelope was not archived.
Strict validation used a reconstructed envelope from the authenticated archived
report and exact capture, with source/module/host/runtime identities checked.
