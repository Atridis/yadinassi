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
