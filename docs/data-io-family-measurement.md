# Data reader/writer workflow measurement plan

Status: **first native capture retained (39 successful cases plus one action error);
revised packet and complete parity pending**. Local interpreter output alone is not
a golden or proof of native parity. This is one coherent
ordinary-workflow batch, not individual API or corner-case measurement requests.

## Primary source and target

The API signatures were checked in the official EDT documentation archive with
SHA-256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`:
`nl/{en,ru}/html/SyntaxHelperContext/objects/catalog63/catalog2375/`
`DataReader`, `DataWriter`, and `ReadDataResult`.
The constructors and ordinary methods date from 8.3.9; reader `CopyTo` from
8.3.10. The existing reviewed native target is Linux 8.3.27.1508, with both server
and managed-client observations. There is no floating-point reader/writer API in
this source; integer methods use unsigned 16-, 32-, and 64-bit values.

Reader sources are a filename, BinaryData, or Stream. Writer arguments differ:
filename construction includes Append before the convertible line delimiter and
WriteBOM, while stream construction has no Append parameter. Writer ByteOrder
is read-only; reader ByteOrder is mutable. Close must distinguish owned streams
from borrowed streams. These facts inform the implementation, but observed
positions, BOM/text behavior, EOF transitions, and result independence remain
native-calibration questions where the first capture does not discriminate behavior.

## Closed packet and wire

- Source: `integrational_tests/measurements/data_io_family.bsl`.
- Source SHA-256:
  `e67d1932d1adaa0b53dc79dcc3995a6c906c5c752364a333fbd25675cacb6e2e`.
- Source size: 8,123 UTF-8 bytes, within the additional 8,192-byte packet bound.
- Forty cases plus two observer controls: 42 emitted messages, five print sites.
- Each successful case encodes at most 40 UTF-16 units as fixed-width hex.
  Exact maximum output rectangle: 7,130 bytes, below the existing 8,192-byte cap.
- Empty-string and supplementary-character observer controls are explicit.
  Action and observer failures have separate finite labels. No exception text,
  arbitrary serialized objects, or platform-specific paths are printed.
- Contract: `scripts/native_1c_data_io_family_contract.py`. It validates framing,
  lengths, order, controls, and availability, **not presumed semantic answers**.

The local checkpoint now includes one closed shared-profile/workflow matrix
entry. Remote publication, native launch and full-fixture execution still require
root coordination. Existing environment, process, credential, input/output and
cleanup limits remain unchanged. Case40 writes a shorter replacement than the
existing file, distinguishing truncation from prefix overwrite while checking
owned-writer close behavior.

## Case coverage

| Cases | Ordinary workflow |
|---|---|
| 01–06 | Byte and unsigned integer roundtrips, default and overridden endian, partial-integer EOF consumption and cursor |
| 07–08 | Whole/partial buffer writes; new/existing-buffer reads and short reads |
| 09–12 | ReadDataResult size/marker fields, exact-read then EOF transition, copied-result independence and independent read streams |
| 13–16 | Writing BinaryData/results, reader CopyTo stream/writer, bounded skip and EOF |
| 17–20 | UTF-8 Cyrillic and supplementary-character ReadChars, default/custom ReadLine delimiters and EOF |
| 21–24 | WriteLine defaults/override, mutable/default encoding, per-call encoding, UTF-8 BOM, converted newline properties |
| 25–26 | Borrowed writer/reader Close and SourceStream/TargetStream identity |
| 27–31 | String/binary/mixed ReadTo markers, longest overlapping marker and index, missing marker, SkipTo found/missing |
| 32–34 | Split with adjacent/trailing separators, mixed separator indexes, fixed-size partial final chunks |
| 35 | DataReader/DataWriter/ReadDataResult type identity |
| 36–40 | Owned filename reader/writer, append, explicit UTF-16 BOM, owned reader/writer Close and overwrite |

## Fixture safety and evidence limits

Each filename case obtains a new temporary root, refuses an existing root, creates
only `a.bin` inside it, and closes readers/writers before deleting that known file.
Root deletion is conditional on an empty directory listing. Unexpected children
are retained, never recursively swept. Failure cleanup follows the same ownership
rules. Tests inject write failure and unexpected child files to verify this.
No user/repository files, arbitrary cleanup targets, network locations, permissions,
or credentials are used.

`!todo` async, exotic encodings, large data, and rare decoder/platform edge cases
remain outside this packet. No environment-dependent raw paths or undefined gap
bytes are compared. Native output, original envelopes, cleanup receipts, and
source/module provenance must be acquired and audited before claiming parity.

## First native acquisition and bounded followthrough

Run41310612604 on8.3.27.1508 captured39 ordinary successful cases and one action error
(case24), with identical client/server output, source/module identity and cleanup checked.
The immutable `tests/fixtures/data_io_family/native-v1` capture preserves all40 records;
it is not a40-case availability/parity claim. The earlier run41309615838 failed input
inventory because of a missing final shell dispatch mapping and obtained no DataIO observations.

Established corrections: incomplete integer reads preserve the byte position; the longest
marker at the earliest matching position wins; ReadChars(all) does not set ReadCompleted;
and a non-appending file writer overwrites from the beginning without truncating the suffix.
The revised same40 packet isolates ByteOrder getter/explicit read, repeated Skip/current
position, one/two UTF16-unit text reads, delimiter error phase, and returned stream
identity/cursor/close behavior. These remain provisional until measured; readonly/lifetime
semantics are not inferred from wrapper identity alone. Cosmetic source compaction keeps
all probes within the unchanged8192-byte input cap; encoded output cap remains7130bytes.
