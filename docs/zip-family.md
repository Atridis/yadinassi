# Ordinary ZIP archive family — local checkpoint

This new standalone family depends on FileIO/BinaryData and the binary-buffer/
stream family. It does not implement database archive formats or provide a
filesystem security sandbox. Native parity is **pending**; no real-1C result has
been acquired for the closed `zip-family-v1` profile yet.

## Ordinary scope

* `ЧтениеZipФайла / ZipFileReader`: file/explicit BSL stream constructors and
  Open, Items, Comment, Extract, ExtractAll, Close.
* `ЗаписьZipФайла / ZipFileWriter`: file/stream and empty constructors, Open,
  Add(file/mask, path mode, recursive mode), Write, GetBinaryData.
* `ЭлементыZipФайла / ZipFileEntries`: Count/Get/Find, read-only indexing and
  iteration. `ЭлементZipФайла / ZipFileEntry`: names/path/extension, original-name
  properties for admitted ordinary names, sizes, modification date and flags.
* Store/Deflate, Minimum/Optimal/Maximum, flat/relative/full stored paths,
  restored/flat extraction, Auto/UTF8 names, archive comments. Full stored paths
  are normalized to relative archive paths; exact native rendering is pending.
* File → archive → file and memory-stream/BinaryData roundtrips. Existing
  destination archive is replaced, not appended. Writer output is fully built
  before publishing; reader source is a bounded snapshot.

Password/nondefault encryption requests fail explicitly. No arbitrary Python
stream/file objects are accepted. No permission or attribute restoration occurs.
The public types/enum values have explicit Type/TypeOf identity and explicit
codec refusal rather than accidental internal serialization.

## Resource and data-integrity boundaries

Compressed input/output and aggregate expanded payload: 16 MiB. Entries and
source-tree scan nodes: 1024. Names/host paths: 4096 characters. Central-directory
count/layout is checked before constructing ZipFile entry objects. Actual
expanded bytes and CRCs/local headers of selected entries (including directories)
are checked before the first extraction write. Nonempty directory payloads,
non-regular entries, encrypted entries and unsupported compression fail.

Absolute/network/device/ADS/traversal names, ambiguous components, NFC-normalized case-folded
collisions, file/directory collisions and symlink/reparse paths are rejected.
Extraction writes are staged and replaced; existing hardlinked targets are not
truncated. On POSIX, directory walks/open/create/replace use no-follow directory
file descriptors. Only verified Darwin system-root aliases `/var→/private/var`
and `/tmp→/private/tmp` are canonicalized first; arbitrary ancestor symlinks are
not resolved or admitted. Unexpected fixture children are preserved, never recursively
removed by the measurement cleanup.

**Temporary platform boundary:** extraction fails closed where directory-fd
anchoring is unavailable, including the current Windows implementation. Reader,
listing and memory/archive construction are not a claim of complete Windows
extraction. A reviewed bounded Windows handle backend remains required for full
cross-platform workflow support. Ordinary explicitly selected writer/source paths
on that platform retain static reparse checks; they are not hostile-writer
confinement. Independent static review identifies no remaining blocker for the current POSIX
anchored / Windows-unsupported extraction scope. It does not certify a Windows
backend or claim dynamic race testing. Publication still requires the root's
source/base and readiness decision.

## Primary source and measurement plan

Pinned official EDT archive `/tmp/json-1c-doc.jar`, SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`:
`nl/{en,ru}/html/SyntaxHelperContext/objects/catalog63/catalog967/` and
`catalog2/catalog968/`. It specifies Items (not Elements), Add(file-or-mask),
Write closing/replacing the archive, and no-argument writer GetBinaryData.

One closed 32-case owned-temp batch covers file/memory creation, reopening,
listing/finding/indexing/iteration/metadata, Store/Deflate and levels, UTF8,
comments, selective/all extraction, relative recursion/flat modes, replacement,
closed/missing-source errors and stream lifecycle. Compare content/relations,
not ZIP bytes, timestamps or absolute temporary path equality. Source identity,
fixed wire/envelope budgets and client/server cleanup are separate gates.

## Explicit deferred scope

`!todo`: encrypted/password archives, multipart/overbudget ZIP64, BZIP2, exotic
encoding and native duplicate-name renaming; OS attributes/permissions;
source-close/borrowed-stream lifetime and unmeasured cursor/default semantics;
Windows anchored extraction backend. Unsupported options are errors, not silent
fallbacks. These limits do not replace the pending ordinary native calibration.

## First real-1C acquisition (preserved, not accepted parity)

Run41261334010 / job124715075898 on head `ee82a3e4bd588df95aa24475275c475d9fc9fd7e`,
tree `4c4c3c36567d834e41ca16e20eaf40e9357e786b`, acquired 30 available observations
and action errors in24/28, with matching client/server capture and verified
container/private-payload cleanup. Capture1408 bytes SHA256
`170a2bc0b1b48939b0f1330a9bf30c2bc9881b741fd8dd71474036f412de15aa`.
The immutable original32 source/output/provenance retain the rejected comparison.
The archived outer transport was not retained: offline envelope validation is a
reconstruction from authenticated report/provenance/capture, not possession of
the original envelope.

Extension is now calibrated without a leading dot. Native recursive archive
count3 versus local2 requires entry-layout evidence; directory support is not
inferred from count alone. The same32 batch now observes bounded entry names/
zero-size markers and a caught Extract outcome in24, and isolates repeated Close
plus subsequent Items access in28. Exact known-owned empty Out/out cleanup is
allowed only after an emptiness check; unexpected children are preserved.
Reserved `!cleanup` records preserve the fixture-failure phase and are explicitly
rejected by require_available, never treated as native parity success. No raw
exception text or random/external full paths are exported. Native32 recalibration
and final exact-head gates remain pending.

## Recursive layout and Close calibration

Run41262403464 / job124718178285 on head `ba9a56084f8c08524e1755fad0564f460135ada7`,
tree `10b819a5b18620f6f95f1a6230a78aaf00e03dfb`, acquired all32 available observations,
client/server-identical and cleanup verified. Capture1590 bytes SHA256
`1fd77f7d971b4e7a13b8ff6d79cd0c098fe4296298a11689b60987e1b7734651`.
Immutable layout32 source/output/provenance retain the original four runtime
mismatches and rejected parity status.

The recursive mask retains a genuinely empty `out/` directory; nonempty `sub/`
is implicit in `sub/b.bin`. Extract succeeded. Therefore the first case24 error
was the fixture's omitted `Out/out` empty-directory cleanup, not an unsupported
Extract operation. Runtime now retains measured empty descendant directories
without relaxing path checks or entry/scan budgets. Public repeated Close raises;
internal reopen/release uses a private cleanup method. Items after Close also
raises. No other mask semantics or source ownership behavior is inferred.

All32 layout observations replay on the anchored local backend; Windows tests
retain the explicit extraction refusal and check the supported observations,
not cross-platform parity. Fresh exact-head native32 and CI remain required.
