# Ordinary file I/O family measurement

`file-io-family-v1` is one batched **measurement**, not a list of predeclared
native answers. It follows the existing reviewed native core workflow and its
server/client module, lifecycle, capture, provenance and cleanup checks. No new
trigger, credential, permission or image is introduced.

## Scope

The 33 cases cover ordinary owned-file workflows together:

1. File name/base/extension/full/path relations (never disclose a temporary path).
2. Directory existence and kind.
3–10. UTF-8 writer bytes, line/EOF reading, count reading, append, overwrite,
Windows-1251, UTF-16 BOM detection, and default writer/reader.
11–14. Base64, string conversion, UTF-8 BOM conversion, binary write and size.
15–18. Copy, move, exact/wildcard search, exact deletion.
19–20. Object type identities and bilingual encoding enum aliases.
21–26. Empty-file EOF, repeated close, unopened read/write and missing-file errors.
27–32. Empty writer bytes, constructor/open reuse, reader reopen, custom
separators, CRLF conversion and UTF-16BE conversion.
33. Temporary-directory availability, unique name/extension and idempotent mkdir.

Signatures and availability were checked against official 1C EDT
`com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`, SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
under `nl/en/html/SyntaxHelperContext/objects/`: File, TextReader, TextWriter,
BinaryData and the relevant Global_context methods. In particular the writer's
file overload has append, not a WriteBOM argument; stream overloads are deferred.

## Ownership and result grammar

Each case obtains a unique name, refuses a pre-existing path, creates that
owned directory, and only addresses literal `a.txt` and `b.txt` beneath it.
Reader/writer close and exact cleanup run on success and exception paths.
The fixture only deletes its root after an empty-directory check; unexpected
children are never recursively swept.
No access to real user files, URL paths, permission attributes or chmod occurs.
No output depends on a temporary filename, wall clock, directory enumeration
order or localized exception text. Host tests place allocations inside their
own `TemporaryDirectory`; no new public BSL APIs are substituted during replay.

Two independently encoded calibration messages precede 33 ordered records.
Each observation is `ok|S<n>:<UTF-16 hex>`, `action-error`, or `observer-error`.
The closed contract caps string length at 56 UTF-16 units and total output at
8192 bytes. Explicit expected-error cases return a short successful observation
from BSL Try/Except; an unhandled error is not silently counted as success.
All 33 records must be observable for availability. Availability and exact
native/interpreter equivalence remain separate gates.

`!todo` marks exotic encodings/streams, permission attributes and cross-platform
wildcard corner cases. These are not a reason to skip ordinary failures.

## Evidence status

Local synthetic contract tests and local interpreter replay are **not native
1C evidence**. A real native run, its immutable source capture and independent
artifact audit must be recorded before claiming native equivalence.


Accepted acquisition: run41215463048, feature head361298f483188c48091ca944d0158a190c6d51a3,
merge9c4d93a6a2fe0a2bda4e2c913e5e65359529d95b,
tree70ff16047d1a48538555a962684a1e2930c806aa. All33 cases matched without
exclusions or probe changes; capture1952 bytes SHA256
`5a5096c2c9c4f2ef1c2190580be2679858a2b513e691c09b7f1f6933cd69b2a4`.
The50-check independent audit bound22 native inputs,9 host inputs,runtime83,
regenerated modules, both ZIP digests, lifecycle/cleanup and isolated replay.
Original transport bytes were not retained; strict validation used a reconstructed
envelope from the byte-verified archived report/provenance/capture. Immutable
output/provenance are retained under `tests/fixtures/file_io_family`.
