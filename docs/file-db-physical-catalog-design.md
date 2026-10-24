# Read-only physical catalog and native contract probe

This next candidate starts from the 415 verified source files of actual main
`9f097437781ffc98a6dd47dcbcc4e358d92170d7`, tree
`3ee079c3de6114533ba8d1e5b40624f4a157b5a8`, after PR #101 merged. It does not extend the accepted
header evidence into a claim of physical-schema or runtime DB compatibility.

## Reader boundary

The independent standard-library reader accepts only storage version 8.3.8.0
with 8192-byte pages initially. Keep the header API unchanged. Read physical
page 2 as the root internal-file header; FAT levels 0 and 1 map logical ranges
to physical pages. Root catalog and description references are logical
256-byte BLOB-block indices within this same root internal file, not physical
object-header page numbers. Description Files entries instead identify physical
data/BLOB/index headers; validate their ranges but do not open them.

Return ordered physical tables, raw field declarations and bounded descriptor
ASTs. No rows, B-trees, writes, repair, metadata-number guesses or BSL DB globals.
Independent limits bound reads, BLOB visits including repeats, output bytes,
tables, fields, tokens and tree depth. Borrowed read callbacks remain borrowed.

Bounds, signatures, exact reads and per-chain cycle checks are structural
requirements. Duplicate physical-page roles, shared logical BLOB tails and
duplicate description IDs are rejected as an explicit supported-subset sharing
policy, not asserted to be universally corrupt. Physical pages backing distinct
logical BLOB blocks may normally be shared. Preserve bounded opaque attributes
and unused pointer padding; do not require zero padding. Unsupported layouts,
invalid structures, resource limits and unsupported sharing stay distinct.

## Native shape probe, not semantic acceptance

Use one new finite `audit_contract` operation at the existing baseline audit
clone, with its existing setup identity and nonprivileged server execution.
The restored audit stays `audit`. Preserve the four-field invocation control,
13 stages, 11 snapshots, CF/DT opaque summaries, process isolation and cleanup.

Call `ПолучитьСтруктуруХраненияБазыДанных` exactly once with a one-element Array
selecting only `Справочник.NativeOracleItems`. The first argument is officially
documented at
https://v8.1c.ru/obuchenie-programmistov/primery-razrabotki/sistemnye_protsedury_i_funktsii/kak_prosmotret_strukturu_tablits_informatsionnoy_bazy.htm.
No second Boolean, unfiltered fallback, external processing or third-party code.

Capture column names, declared type lists and observed nested ValueTable column
signatures before hard-coding nested schema. Do not serialize scalar cells,
metadata objects, native schema values, row data, references or exception text.
Bound every name, type string, count, traversal and final encoded envelope.
Unobserved nesting is not verified empty. Bind the result to exact staged source,
nonce, operation token, baseline digest, platform version and verified cleanup.

A separately versioned strict report contract must distinguish `shape_captured`
from reader acceptance and retain the full 32768-byte transport ceiling. Prove
the maximum encoded whole report, including worst-case strings, source hashes,
failure diagnostics, 11 snapshots, comparisons and cleanup; a manifest-only
sub-budget is insufficient. Exhaustion fails closed, never truncates or raises
the cap. Historical v2 evidence is not retroactively upgraded.

## Verification and rollout

Synthetic tests cover FAT addressing, fragmented pages, BLOB cycles and bounds,
descriptor grammar, sharing policy, budgets and stream ownership. At 8192-byte
pages aligned 256-byte BLOB blocks cannot straddle logical pages: test range
reads crossing page boundaries and fragmented chain jumps instead.

Probe tests reject stale or forged bindings, partial publication, extra keys,
bad identities, limit exhaustion, missing completion and failed cleanup. After
shape review, a separately scoped allowlisted native schema-value comparison
must establish actual physical names; never guess `_ReferenceN` or `_FldN`.

Independent review and aggregate local gates are required before publication.
PR #101 is merged; the separate main follow-through remains a release gate. No native
compatibility claim until the exact new source completes its relevant native
verification. This design and local tests alone are not native evidence.

## Implemented local reader interface

`yadinassi.storage.filedb_catalog.inspect_catalog(path, limits=CatalogLimits())`
owns and closes its read-only file descriptor. The caller must provide a trusted,
consistent offline copy. `read_catalog(read_at, file_size, limits=...)` and
`CatalogReader(read_at, file_size, limits=...)` borrow a positioned callback that
returns exact bytes. The reader does not close the callback's backing resource.
`reader.root.read_range(offset, length)` exposes bounded root-file navigation;
all calls share that reader's cumulative budgets. Catalog collection is single-use.

Results are frozen dataclasses and ordered tuples. `PhysicalCatalog` retains
physical table/field declarations, raw descriptor ASTs and bounded opaque bytes;
its capability is only `physical_schema_read_only`. `InvalidStructure`,
`UnsupportedLayout`, `UnsupportedSharing` and `ResourceLimit` are distinct
exception classes with finite reason codes. Source I/O and observed concurrent
metadata changes are diagnosed separately. No exception returns native payload
or operating-system error text. The module also loads standalone without an
Interpreter import; ordinary package import retains the package's existing
embedding behavior.
