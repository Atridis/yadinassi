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
- SHA-256 `237b2b7df6ec9a16c1e17956b4bfc57c3d8b3cf1826d695fecae1a9e288b6602`
- 6,989 UTF-8 source bytes; additional packet bound 8,192 bytes.
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
| 25–29 | Stream count omitted, partial, zero, over-EOF/at-EOF, nonzero source position and resulting cursor |
| 30–31 | Closed-stream rejection/state preservation; borrowed read-only view/shared cursor remains usable |
| 32–35 | Read-only properties, invalid Append/count/constructor arguments, type/enum identity |
| 36–40 | Each algorithm: mixed prefix + owned AppendFile + suffix, missing-file rejection/state preservation |

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
