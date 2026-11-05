# Section Query validation plan

This increment implements a bounded local section-query contract, not native 1C
compatibility. Historical development runs on the older, unintegrated section
query patch reported 37 focused, 217 regression, and then 39 expanded focused
tests. Those logs are not evidence for this later merged source: the qualifier,
SQLite recovery and metadata stack have since changed. A fresh source-bound
run must be separately approved and recorded for the exact candidate.

The current focused section suite contains 45 local test methods: 3 parser,
22 section-scan and 20 query methods. Two query methods additionally check a
hostile ambient Decimal context and UTF-16 string bounds at the logical port.
No native section-query observation is implied by these tests.

## Focused checks

From the repository root, after approval (POSIX shell):

```sh
PYTHONPATH=.:tests python -m unittest -v \
  test_section_query_parser test_catalog_section_scan test_catalog_section_queries
```

Expected scope:

- Grammar: one optional section component, English/Russian syntax, aliases and
  parameters; rejection of joins, nested paths, wildcards, expressions and SQL.
- Logical port: owner/section/row identities, exact scalar and reference types,
  owner Ref filters, casefold policy, ordering and more than 1,000 total rows.
- Cursor isolation: single-use tokens bound to source, catalog, section,
  predicates, ordering, page size and comparison policy; closed/write views and
  catalog/section traversal changes refuse inappropriate continuation.
- Snapshot/isolation: a second backend stages writes while the pinned reader
  consumes multiple pages and repeats a traversal. The reader sees old data;
  after it closes and the writer commits, a fresh view sees the new rows. This
  reflects DELETE-journal locking rather than claiming an overlapping commit.
- Catalog scope: authored backend schemas may reuse section UUIDs across
  catalogs; owner/row UUID reuse still cannot mix tables, rows or tokens.
  The XML importer's global metadata-UUID admission rule remains unchanged.
- Integrity: malformed UUIDs, noncanonical numeric/date values, missing owners,
  dangling references and noncontiguous positions fail even outside the filter.
- Resource limits: source/per-owner row and byte bounds refuse before payload
  fetch; TOP does not bypass admission. The scanner never flattens owner cards
  or fetches another section's payload.
- Runtime: typed scalar Unload, reference Unload refusal, detached old/new
  results, no visibility of unsaved buffers, preserved rows on deletion marks,
  exact reference target/database/metadata scope, hostile pages and cleanup.
- Compatibility boundaries: v3 read-only scan and unsupported legacy section
  scans, without migrations or write capabilities being introduced.

Timing varies by host. Announce the exact test set and wait for approval before
running any local tests. Record the source tree, command and result.

## Affected regression checks

After focused checks pass, run:

```sh
PYTHONPATH=.:tests python -m unittest -v \
  test_query_parser test_catalog_queries test_catalog_scan \
  test_sqlite_catalog_backend test_sqlite_catalog_layout \
  test_sqlite_catalog_physical_layout test_sqlite_catalog_sections \
  test_sqlite_catalog_section_layout test_sqlite_catalog_runtime \
  test_catalog_tabular_runtime test_configuration_tabular_sections \
  test_catalog_deletion_mark test_database_context
```

The historical 217-method regression count and its 3.089-second result apply
only to the earlier unintegrated source, not the current candidate. Use a fresh
pinned test inventory for the merged source, including `test_query_parser`, and
record exact source, commands, environment, result counts and logs. Focused
success does not replace the repository's full unit suite and platform CI.

## Separate native evidence

No native execution is required to define this local storage/read-port contract.
Before claiming native section-query compatibility, separately review and
authorize a source-bound official XML fixture and bounded output packet covering:

- section source naming, explicit/implicit aliases and owner Ref semantics;
- selected custom scalar/reference values and column names/types;
- filtering, ordered selection, cursor boundaries and scalar Unload metadata;
- row numbering only if a later increment exposes it, including deletion and
  reordering rather than inference from SQLite positions;
- official export/redump and nested metadata inventory admission.

Existing owner-only Query24 and catalog XML observations do not establish these
section behaviors. Keep native observations unchanged. This increment neither
widens Designer XML activation nor changes UI, migration or integration lanes.

## Integration with scalar SQL scans

The current-main integration keeps owner Query on `scan_catalog_values`, with
SQL projections on v2/v3 and the bounded v1 fallback. Section sources use their
separate read-only scan. Regression checks cover all six directions of cursor
mode changes between full cards, scalar projections and sections, no section
table reads from owner Query, no owner projections from section Query, and
exact UUID validation before interpreting logical-port identities. Full supplied
pages are validated even when their tail is beyond TOP. The section source
still uses bounded in-memory sorting after complete source validation; the
owner SQL optimization does not imply an SQL section-query optimizer.
