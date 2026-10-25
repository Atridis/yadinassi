# Offline .1CD header inspection (experimental)

`yadinassi.storage.filedb.inspect_header(path, *, max_pages=4294967295,
max_file_bytes=281474976645120)` is a small Python API for inspecting the header
and physical length of a **caller-provided consistent offline copy**. There is
no CLI, BSL API, live connection or automatic snapshot in this inspection module.
The separate [optional file-database context](file-database-context.md) integrates
this inspector with Interpreter and `--f`; it does not add a native session or
strengthen the header-only validity guarantees below.
The implementation uses only Python's standard library; importing through the
existing `yadinassi` package still loads its normal interpreter dependencies.
The native test harness stages the same source as a standalone module, without
importing that package or loading Interpreter dependencies.

```python
from yadinassi.storage.filedb import inspect_header, InspectionStatus

result = inspect_header("offline-copy.1CD", max_pages=1000000)
if result.status is InspectionStatus.HEADER_LAYOUT_MATCH:
    print(result.header.version, result.header.page_size, result.header.page_count)
else:
    print(result.status.value, result.reason.value if result.reason else None)
```

## Contract and boundaries

- Opens read-only, checks regular-file type, reads at most 24 bytes in total and
  compares `fstat` metadata before/after on the same descriptor. No writes,
  repair, extraction, memory mapping or page-count-dependent allocation/read.
  Short reads are accumulated until 24 bytes or EOF, without exceeding that budget.
  `O_NONBLOCK` is used where available to avoid blocking on FIFO open.
- Paths and symlinks are followed normally. The caller must provide a trusted
  snapshot path, not an arbitrary device or an actively modified database.
- Changed device, inode, mode, size, modification time or change time yields
  `changed_during_read`. Access time is excluded because reading may update it.
  Equal metadata **does not prove consistency**: timestamps may be coarse,
  mutations may be invisible and a copy itself may already be inconsistent.
- `header_layout_match` means only that the recognized header and physical
  length agree. It is **not** “valid database”, native compatibility, integrity,
  transactional consistency or a guarantee that reading a live DB is safe.
- Tables, rows, root pages, allocation maps, BLOBs, indexes, configuration
  semantics, `.cf` and `.dt` are not read or validated. No native binary fixtures
  are redistributed; measured compatibility requires separate source-bound evidence.

## Pure decoder and native-measurement boundary

`decode_header(raw, size, *, max_pages=4294967295,
max_file_bytes=281474976645120)` performs the same checks without opening any
file. `raw` must be exact `bytes` of length at most 24; `size` must be a
nonnegative exact integer. Invalid arguments raise `ValueError`, including
booleans, bytes subclasses, mutable buffers, and oversized prefixes. Limits
have the same exact-type and range guards as the path API. The caller owns
acquisition, file identity and snapshot consistency. Unknown complete versions
are dispatched before geometry or policy checks and never produce page facts.

The opt-in [native oracle v2](native-file-db-oracle.md) retains at most 24 bytes
from each of its existing destination hash passes on the same verified,
descriptor-relative no-follow file. Hashes, prefixes and all existing identity
checks must agree before decoding. It does not reopen the payload through
`inspect_header(path)`. Only frozen DB snapshots receive header facts; CF/DT
remain opaque. Its unchanged 64 MiB file cap and stricter page-count bound are
passed explicitly. A failed decode produces only the existing `invalid_header`
failure kind; it never exports rejected bytes or guesses geometry.

This measurement path does not itself establish native evidence. Its report schema 2
cannot be substituted for historical schema 1 reports, which did not decode
headers. A fresh source-bound native run is required before making a measured
compatibility claim. Even that claim is limited to observed header geometry,
not tables, rows, transaction consistency or full database validity.

## Exact format dispatch

Bytes 0–7 must be ASCII `1CDBMSV8`. Bytes 8–11 are four unsigned version bytes,
not the installed platform version. Only the following exact tuples are accepted:

- `8.2.14.0`: at least 20 header bytes; implicit 4096-byte pages. Bytes 20–23
  have no meaning to this parser and are ignored.
- `8.3.8.0`: at least 24 header bytes; bytes 20–23 are a little-endian unsigned
  page size, one of 4096, 8192, 16384, 32768 or 65536.

Every other complete version is `unsupported_format`, before interpreting any
version-dependent field or layout/policy limit. There is no heuristic fallback.
Bytes 12–15 give the little-endian unsigned 32-bit page count. Bytes 16–19 are
opaque and ignored. Physical length must be aligned to page size and exactly
equal to page count times page size. A three-page minimum is a conservative
acceptance policy, not proof of the full format or proof that smaller files are
corrupt.

## Results and limits

`HeaderInspection` and `FileDBHeader` are frozen dataclasses. Successful results
contain only version, page size, page count and physical file size. Other results
have no header facts. Finite enums provide status and optional reason; no paths,
raw headers, opaque bytes or underlying OS exception messages are returned.

- `invalid_layout`: truncated header, wrong magic, invalid supported-format page
  size, unaligned length or page-count mismatch. This is a failed header/layout
  check, not an exhaustive diagnosis of database corruption.
- `unsupported_format`: unknown complete version.
- `policy_limit`: fewer than three pages, caller page-count limit or caller
  physical-byte limit. Layout checks precede policy checks, so malformed files
  are not mislabeled merely because they also exceed a limit.
- `changed_during_read`, `not_regular_file`, `io_error`: acquisition failures.
  Some operating systems reject opening a non-regular file before it can be
  classified; that produces `io_error`.

Both caller limits must be exact positive integers (booleans excluded), no larger
than the uint32 page-count ceiling or that ceiling times 65536 bytes,
respectively. Bad arguments raise `ValueError` before opening. Defaults express
format arithmetic ceilings, **not** a tested database-size compatibility claim.
Even maximum counts do not cause large allocation. These limits bound accepted
facts; the physical read budget is always independently fixed at 24 bytes.

## Evidence and verification

This is original small header-validation code, not a translated table reader.
The format facts were cross-checked against the MIT-licensed reference
[Infactum/onec_dtools database_reader.py](https://github.com/Infactum/onec_dtools/blob/master/onec_dtools/database_reader.py)
and [official page-format documentation](https://its.1c.ru/db/content/metod8dev/src/admins/file_variant/i8105924.htm).
The [older official article](https://its.1c.ru/db/content/metod8dev/src/developers/platform/metod/i8105710.htm)
is dated for platform 8.3.4 and must not be generalized to modern formats.
No upstream fixture is redistributed or assumed to be freely redistributable.

Focused tests use independently constructed synthetic headers and small temporary
sparse files (at most three 64-KiB pages); the uint32 ceiling uses mocked file
metadata, not a huge real file. They do not establish native 1C interoperability.

```sh
python -m unittest discover -s tests -p test_filedb_header.py -v
```
