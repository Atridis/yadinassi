# Bounded ordinary data-reader/writer workflows

**Local implementation checkpoint; native calibration is pending.** This is one
coherent new family, not additional general stream permissions. The primary
reference is the official EDT2026.2 archive
`com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`, SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`, under
`SyntaxHelperContext/objects/catalog63/catalog2375/{DataReader,DataWriter,ReadDataResult}`.
These APIs date from8.3.9, CopyTo from8.3.10; acquisition targets8.3.27.1508.
The documented integers are **unsigned**, with no floating-point API in this family.

## Ordinary complete workflows

- `ЧтениеДанных / DataReader`: construct from a local filename, BinaryData or an
  admitted MemoryStream/FileStream/Stream. Read/ReadIntoBinaryDataBuffer, byte and
  16/32/64-bit integer reads, ReadChars/ReadLine, Skip/SkipTo/ReadTo, Split,
  SplitInPartsOf, CopyTo, SourceStream and Close.
- `ЗаписьДанных / DataWriter`: construct from a local filename or admitted stream;
  file append, explicit BOM, encoding/endian/line settings; Write(BinaryData or
  ReadDataResult), WriteBinaryDataBuffer, byte and 16/32/64-bit writes,
  WriteChars/WriteLine, Flush, TargetStream and Close.
- `РезультатЧтенияДанных / ReadDataResult`: readonly Size/MarkerFound/MarkerIndex,
  GetBinaryData/GetBinaryDataBuffer and OpenStreamForRead. It has no public
  constructor; independent result bytes survive closing their original reader.
- TextEncoding and line settings are mutable; Reader.ByteOrder is mutable and
  Writer.ByteOrder readonly. Reader.ReadCompleted initially False follows short
  read detection, rather than simply checking the physical cursor at end.
- Close releases owned file/binary streams, not caller-owned streams. Readonly
  mutation and existing buffer capacity checks remain authoritative.

UTF-8/UTF-16LE/UTF-16BE and the existing finite FileIO codec allowlist are reused.
A selected ReadChars prefix is decoded without interpreting later mixed binary
or differently encoded fields. Line reading likewise decodes only its selected
line. Strict decode errors preserve the logical reader position.

## Bounds and authority

Existing16MiB stream/file/buffer caps remain unchanged. Marker count is at most64,
each marker at most4096bytes; result partitions at most4096. Each marker operation
has a64MiB scan-work allowance, counted over every searched remaining span and
marker, not reset per output part. Bounds are local admission policy, not claims
about native maximums. Text encoding/conversion growth is checked before output
allocation; failed partition construction does not advance the source cursor.

Only exact built-in stream/buffer/array types are admitted. The existing
FileStream pre-open local path/device/UNC/ADS rules and opened regular-file checks
are reused. No networking, arbitrary host stream callbacks, permission changes,
recursive cleanup or external codec loading is introduced. Optional argument
holes are admitted only for exact stored new-family receivers/constructors;
other host calls retain their existing side-effect guard.

## Deliberate gaps and calibration

`!todo`: Async/Begin methods, exotic/stateful ICU codecs, malformed-byte replacement,
read-result codecs/typed cells, arbitrary third-party/nonseekable streams and
unmeasured overlapping-marker/Unicode-split edge behavior. No fallback into a
host network stream or unbounded parser is provided. Integer partial-read cursor,
BOM defaults, Unicode ReadChars units, marker ordering, empty split results and
EOF/lifecycle details are provisional until the single closed native40 batch.

The packet uses short fixed data and verified owned temporary paths, exposes only
bounded relation/value observations, and preserves unexpected fixture children.
Public capture fixtures will contain only fixed measurement source, bounded raw
observations and minimal source/platform identity; private installation/session/
audit/authentication reports will not be published. See
[data-io-family-measurement.md](data-io-family-measurement.md).
