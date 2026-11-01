# Ordinary binary buffer and stream workflow

## Status and primary source

Implementation checkpoint on main `f1549f9a53fb12d5d6ceca02d3bc78e5d17e2955`.
The single `binary-stream-family-v1` native batch has an initial incomplete
acquisition (28 available cases, 12 action errors); see the immutable evidence
below. Explicit-origin remeasurement and final parity remain pending. Local
tests are not evidence of native parity; ordinary observations are calibrated
in this same feature before acceptance.

Primary reference: official EDT documentation archive SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
`nl/{ru,en}/html/SyntaxHelperContext/objects/catalog63/catalog2375/`:
BinaryDataBuffer, MemoryStream, FileStream and Stream, their constructors,
properties and methods; corresponding system enums and global conversion pages.
The archive is reference material, not newly redistributed in this change.

## Supported ordinary workflow

* `BinaryDataBuffer/БуферДвоичныхДанных`: fixed-size byte storage, indexed
  read/write and iteration, Size/ReadOnly/ByteOrder, Get/Set, unsigned
  ReadInt16/32/64 and WriteInt16/32/64 with explicit/default byte order.
* GetSlice shares storage; Read and Copy copy bytes; Concat and Reverse create
  new buffers. Write validates ranges before mutation and snapshots overlapping
  source bytes. SetReadOnly blocks mutation through that buffer.
* `MemoryStream/ПотокВПамяти`: empty expandable storage, initial-capacity
  constructor (not initial size), or fixed-capacity shared BinaryDataBuffer.
* `FileStream/ФайловыйПоток`: Open/Create/CreateNew/OpenOrCreate/Truncate/Append;
  Read/Write/ReadAndWrite access; FileName. Optional bounded buffer-size argument
  is validated; the implementation uses an unbuffered descriptor.
* Common streams: CanRead/CanWrite/CanSeek, CurrentPosition, Size, Seek with
  Begin/Current/End, Read/Write, SetSize, CopyTo, Flush and idempotent Close.
  GetReadonlyStream shares storage and cursor but blocks writes.
* MemoryStream.CloseAndGetBinaryData, BinaryData.OpenStreamForRead (independent
  read cursors), BinaryData.Write(stream), and the exact one-argument globals
  GetBinaryDataFromBinaryDataBuffer/GetBinaryDataBufferFromBinaryData.
* The Stream identity represents returned views; it has no public constructor.
  All eight added value/enum types explicitly reject internal serialization.

## Data integrity and bounded resource policy

These are Yadinassi implementation limits, not inferred native platform limits:
16 MiB per buffer/stream/file and per seek position, strict finite integral
indices and byte values, and no implicit coercion of booleans, strings or host
objects. Concat/growth/CopyTo and read/write ranges are checked before mutation.
Invalid destinations do not consume source bytes. OS write failures can still
leave partial writes, as with ordinary file I/O; this is not transactional storage.

File descriptors are checked with fstat for regular-file type and bounded size
**before truncation**. Nonblocking open avoids hanging on special files, and
all rejected-open paths close the acquired descriptor. UNC, Win32/NT device
namespaces, DOS device names and alternate-data-stream path forms are rejected
before open (also on non-Windows hosts); ordinary drive-qualified paths remain
available. This deliberately excludes exotic namespace/path forms. No arbitrary Python
stream adapters, network URL schemes, device I/O, chmod, permission changes or
recursive cleanup are provided. Existing explicit local-file authority is not
broadened into network or arbitrary cleanup authority.

Unspecified extension/gap bytes are zero-filled locally; native tests do not
assert their values. Close and exceptional cleanup must not leak owned file
handles. The batch creates fresh collision-checked temporary directories,
uses only its exact owned file, rejects unexpected residual children, and
cleans those owned paths on both success and failure. It never uses repository
or user files as fixtures. Platform-specific paths are compared relationally.

## Deferred scope (`!todo`)

DataReader/DataWriter, FileStreamsManager, async/Begin APIs, buffer Split and
bitwise operations, broad buffer text/hex/base64 conversions, TextReader/
TextWriter/JSON/XML stream overloads, fixed-buffer SetSize changes, exact
cross-process sharing locks, OS-specific errors and sparse-file behavior.
Native calibration of shared-view close propagation and ordinary constructor/
seek defaults remains a required gate, not a claim hidden under `!todo`.

## First real native acquisition and explicit-origin calibration

[Run 41254621539](https://github.com/Atridis/yadinassi/actions/runs/41254621539)
on PR173 head `3e22a0d8dad8674df789edb561854a44c515dbb2`, tree
`852ca6c22214b4ee7b469ac8e91e648ccb3b68b3`, acquired matching client/server
captures: 1565 bytes, SHA256
`05b6753fb5625ac273e048fddcd84b276d16cbf8a1afea18168f8f8a9d15747b`.
The 40-case source is SHA256
`ad3cd0f8ded26e1aa142cfad09c0854ae3214aaf837fdf07dbef5e774d2aff82`.
**Only 28 cases were available; cases16/17/18/19/21/22/23/24/26/30/33/39
reported action-error. Runtime parity was rejected.** All failed paths invoked
Seek with omitted initialPosition. This common factor motivates, but does not
by itself prove, the default-argument diagnosis.

The original source, capture and failed acquisition provenance remain immutable
under `tests/fixtures/binary_stream_family/original40*`. Availability checks still
reject that capture. The revised broad batch uses explicit Begin in ordinary
workflows and retains case17 as an isolated omitted-origin observation. Runtime
omission behavior is not changed before that native observation is obtained.
No raw exception text, native permissions, or resource caps are changed.

The archived outer transport was not retained. Offline validation reconstructs
its envelope from exact archived report/provenance/capture bytes; it is not a
claim to possess the original envelope. Cleanup and source/runtime identities
were checked independently. These are acquisition facts, not final acceptance.
