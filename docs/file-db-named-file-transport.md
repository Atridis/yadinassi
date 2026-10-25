# Experimental PARAMS/DBNames extraction

The standalone `yadinassi.storage.filedb_named_file` module implements only
single-part PARAMS/DBNames extraction from a caller-owned consistent offline
1CD copy. Its `read_dbnames(read_at, file_size, *, profile, limits=None,
catalog_limits=None)` returns immutable decompressed bytes, fixed target/profile
identifiers, packed byte count/SHA-256, and combined cumulative usage. No source
rows, descriptors, timestamps, internal addresses or duplicate packed payloads
are retained in the result. The source callback is borrowed, never closed or
written. No filesystem/native operation, runtime/CLI integration, BSL wrapper,
metadata parser, logical mapping, CONFIG/CONFIGSAVE or multipart support is added.
Existing RecordProfile codecs and lazy FileDBContext behavior are unchanged.

## One explicit profile, not a learned layout

The frozen `DBNamesProfile(declarations, recordlock, format_item)` constructor
requires all three inputs. The public `DBNAMES_DECLARATIONS` tuple provides the
only admitted exact vector, without supplying an implicit/default profile:

- FILENAME, NVC, 0, 128, 0, CI
- CREATION, DT, 0, 0, 0, CS
- MODIFIED, DT, 0, 0, 0, CS
- ATTRIBUTES, N, 0, 5, 0, CS
- DATASIZE, N, 0, 20, 0, CS
- BINARYDATA, I, 0, 0, 0, CS
- PARTNO, N, 0, 10, 0, CS

Recordlock must be the string "0" and format the exact integer 0. Booleans,
changed spelling/primitive attributes and alternate vectors are rejected.
The profile identifier is `params_dbnames_8380_8192_v1`. Its explicit hypothesis
is one status byte, declaration order, no hidden version/null prefix, widths
258/7/7/3/11/8/6, and stride 301. Offsets are derived from those widths, never
provided by the caller or searched in source bytes. Reserved slot zero must
have marker 1; every later slot must have marker 0. Other free/unknown markers
are unsupported. Exact stride divisibility and slot bounds are checked before
row access. There is no observed-row-count constant or alternate-layout retry.

The ordered declarations, lock and integer-zero format were observed by the
finite Phase-A capture. That capture did not observe row boundaries, filenames,
BLOB payloads or content equivalence. The framing and codec rules above were
separately pinned as one source-justified, falsifiable hypothesis before native
extraction. Synthetic tests prove implementation behavior, not native layout.
Native extraction evidence requires a separately audited source-bound run;
the library result always says `experimental_named_file_bytes` and
`native_acceptance=pending`, never certifying its own compatibility.

## Narrow row selection and codecs

Require one table with the fixed ASCII case key PARAMS and match the profile's
exact declaration spelling/lock/format before opening its data. Scan all slots,
not just until the first filename match. FILENAME is a little-endian u16 UTF-16
code-unit length, at most 128, followed by strict UTF-16LE. Only ASCII case folding
matches DBNames; duplicate/case-variant matches fail. No Unicode normalization,
substring search, alternate names, or returned unrelated filenames is allowed.

Only the selected row's DATASIZE, BINARYDATA and PARTNO are decoded. Dates and
attributes contribute widths but remain opaque. N(20,0) size and N(10,0) part
require sign nibble 1, high-first decimal digits 0..9, and zero final low padding.
Sign 0 (including negative zero) and other signs/padding fail. Integers are
assembled directly without floating-point/Decimal context. DATASIZE must be
positive, PARTNO exactly zero, and BINARYDATA two nonzero little-endian u32 values
(start, packed length). Size must equal packed length before any BLOB allocation.
Unrelated transport fields and BLOB bodies are never decoded or read. Empty or
reserved-only data cannot yield a successful extraction.

These widths and encodings were independently derived from pinned Tool1CD
FieldType.cpp, Table.cpp, BinaryDecimalNumber.cpp and Common.h facts at commit
`d5e31816f4c9b11a445f73fc92d08803840ce599`. They are not an official format
specification. No upstream implementation was copied, translated or executed:
[FieldType.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L138-L155),
[Table.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L418-L438),
[BinaryDecimalNumber.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/BinaryDecimalNumber.cpp#L186-L203).

## Shared object boundary

A CatalogReader must first finish its catalog, then successfully open the chosen
PhysicalTable's data object. Its private `_open_table_blob` accepts only that
identical table object, once. Files[1] must be nonzero and have the already
reserved `table_blob_header` role. The ordinary internal-file mapper claims all
BLOB FAT and data pages through the same source and cumulative budgets. Index
contents remain unopened. Physical page overlap with root objects, descriptors,
table data, FAT pages, or any reserved table header is rejected globally.

A `_TableBlobStore` owns logical blocks only within that selected BLOB internal
file, independently from root catalog chains. Logical indices are not physical
page numbers. Blocks are 256 bytes: a little-endian uint32 next index, uint16
used length at offset 4, and up to 250 payload bytes at offset 6. Index zero is
reserved and next zero terminates. Declared nonzero packed length is exact:
short/long chains and nonzero next after the declared byte count are rejected.
Zero-payload intermediate blocks are allowed but consume visit bounds. Cycles,
range errors, and sharing a previously owned logical block fail. Distinct blocks
on one backing physical page are allowed.

These mechanical facts were independently implemented from pinned descriptions
of Tool1CD Table.cpp and Common.h at commit
`d5e31816f4c9b11a445f73fc92d08803840ce599`. No upstream implementation was copied,
translated, or executed. Little-endian interpretation is the explicit supported
hypothesis, not an official format specification:
[Table.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L729-L787),
[Common.h](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Common.h#L44-L49).

## Bounded raw DEFLATE

Transport defaults are 1 MiB packed, 8 MiB plain, 8192 chain visits and
4096 inflate calls. Hard ceilings are 16 MiB, 64 MiB, 131072 visits and 65536
calls. All limit values must be positive exact integers, not booleans. `NamedFileLimits` also bounds slots and record bytes to 4096 each by default,
with 65536 hard ceilings. All six bounds are enforced independently; they are
policy values, not native format maxima.

Inflation admits exactly one raw DEFLATE stream (`wbits=-15`), feeds at most
32768 bytes and requests at most 65536 output bytes per call. Output requests
include a budgeted one-byte overflow probe. Unconsumed input is processed before
new input. EOF is mandatory; missing EOF, malformed codes, trailing bytes,
concatenated streams, and nonprogress fail with finite codes. No flush, wrapper
retry, plaintext fallback, dictionary, or nested decompression is used. A valid
empty DEFLATE stream is valid transport; absent compressed input is not.

Catalog read/process/output budgets remain cumulative across catalog, table
data, table BLOB, and inflation. Chain assembly and the immutable result are
reserved before allocation; logical-read callback/assembly/copy scratch and
payload slices are charged separately. Each inflate call reserves its maximum
output, assembly copy, possible unconsumed/unused input, and processing work
before entering zlib. The final immutable plaintext copy is also reserved.
Charges are intentionally conservative: independent catalog budgets can reject
an input below the transport byte limits. These are representation/work bounds,
not exact Python/native-zlib heap bounds or wall-clock guarantees. The isolated
caller's deadline remains the outer time boundary. See the
[Python zlib API](https://docs.python.org/3/library/zlib.html).

Synthetic tests exercise the exact profile, row selection, strict codecs,
transport bounds and object ownership. They provide no evidence of DBNames
native byte equivalence or metadata mapping. Public evidence must project only
fixed identifiers/counts/digests and the limited extraction outcome; the library's
own digest cannot establish independent content equivalence.
