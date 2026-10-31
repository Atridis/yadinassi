# Ordinary local file, text and binary I/O

One coherent new-functionality block, based on official EDT syntax help
`com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar` (SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`).
Documentation supplies signatures, not a claim of observed native behavior.
Native run [41215463048](https://github.com/Atridis/yadinassi/actions/runs/41215463048)
on published head `361298f483188c48091ca944d0158a190c6d51a3` accepted all **33 cases**:
client/server/interpreter match exactly (1952 bytes, SHA256
`5a5096c2c9c4f2ef1c2190580be2679858a2b513e691c09b7f1f6933cd69b2a4`).
Independent artifact/source/module/lifecycle/replay audit passed 50 checks.
The original transport envelope was not archived; its validator was rerun on
a reconstruction from byte-verified archived report/provenance/capture.
Immutable capture and provenance: `tests/fixtures/file_io_family/native33*`.
This is Linux 8.3.27.1508 evidence for the finite batch, not universal parity.
Full/OS gates are separate; unit tests alone are not native evidence.

## Implemented scope

- `Файл / File`: constructor, read-only Name/BaseName/Extension/Path/FullName,
  Exists, IsFile, IsDirectory and Size, with bilingual names.
- TempFilesDir, GetTempFileName (name only; does not create a file),
  CreateDirectory, CopyFile, MoveFile, nonrecursive FindFiles, exact-path
  DeleteFiles for files and empty directories. Returned search entries are File
  objects. All are local OS paths, not URLs.
- `ЧтениеТекста / TextReader`: empty/file constructors, Open, Close, Read,
  ReadLine. Empty lines are distinct from Undefined at EOF. Bounded snapshot
  reading closes the underlying descriptor immediately.
- `ЗаписьТекста / TextWriter`: empty/file constructors, Open, Close, Write,
  WriteLine, append and configurable line separators. File lifetime ends on
  Close or object disposal. Invalid encoding/argument validation precedes file
  truncation. Normal default/BOM/newline cases are included in the accepted native batch.
- `КодировкаТекста / TextEncoding`: UTF8, UTF16, ANSI, OEM, System; explicit
  UTF-8, UTF-16LE/BE, Windows-1251, CP866, ASCII, Latin1 and KOI8-R names.
  ANSI/OEM currently model the Russian target; System uses the host locale.
- `ДвоичныеДанные / BinaryData`: file constructor, immutable bytes, Size and
  Write; Base64String/Base64Value and GetBinaryDataFromString/
  GetStringFromBinaryData, including explicit encoding/BOM conversion.
- Type/TypeOf register the four value classes and encoding enum. Internal
  serialization and cross-context transport are not inferred from these types.

## Safety and resource boundaries

Reads/writes open nonblocking, inspect the actual descriptor, reject nonregular
files and bound data to 16 MiB. This is a Yadinassi resource budget, not a native
1C limit. Directory searches inspect at most 100,000 entries. File exceptions
are converted to ordinary catchable BSL errors. Explicit local operations still
have ordinary filesystem effects and permissions; this is not a new sandbox.

All tests and native probes use fresh owned temporary paths. Copy/move/delete
never target user files or repository directories. Native probes compare path
relations rather than equality of randomly generated paths across contexts.
Cleanup is explicit and bounded to the fixture's fixed names. There is no
session-wide temporary-file garbage collector.

## Deferred `!todo` scope

Stream/async overloads; ICU-only codecs and malformed-byte replacement;
platform-specific sharing locks and concurrent-reader snapshots; modification
attributes and permission setters; UNC/foreign-platform path semantics;
recursive searches and wildcard/recursive deletion; cross-filesystem MoveFile;
exact diagnostics, unusual separators/surrogates and incompatible-encoding
append. These limitations are explicit in code rather than hidden behind a
broad claim of full platform compatibility. Ordinary failures, cleanup and data
integrity remain tested now, not deferred as corner cases.
