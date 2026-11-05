# Catalog scan cost and integrity boundaries

The repeat-audit regression uses temporary owned SQLite databases, never native
1C or user databases. Baseline is main `1b0c182e16ad35ff8ac1045455c9812509373f0c`.
Each fixture has N owners, either zero or two empty sections, no custom owner
fields, and a unique four-digit code. The request is exact `code = value`,
`page_size=1`; hit selects the final code and miss selects an absent code.

SQLite tracing starts **after** `begin_read()` and stops before closing the view.
The counts below cover scan SELECT statements, not backend opening, metadata
activation, transaction setup, or later reference-member reads. Scalar mode
requests only `('code',)`. Full-card materialization counts `_card` calls.
The fixture is independently rebuilt for each version/mode.

| N | Sections | Outcome | Baseline SELECT | Full-card SELECT | Scalar SELECT |
| ---: | ---: | --- | ---: | ---: | ---: |
| 1 | 0 | hit | 4 | 5 | 5 |
| 1 | 0 | miss | 4 | 5 | 5 |
| 1 | 2 | hit | 10 | 14 | 5 |
| 1 | 2 | miss | 10 | 12 | 5 |
| 100 | 0 | hit | 4 | 5 | 5 |
| 100 | 0 | miss | 4 | 5 | 5 |
| 100 | 2 | hit | 604 | 14 | 5 |
| 100 | 2 | miss | 604 | 12 | 5 |
| 1000 | 0 | hit | 4 | 5 | 5 |
| 1000 | 0 | miss | 4 | 5 | 5 |
| 1000 | 2 | hit | 6004 | 56 | 5 |
| 1000 | 2 | miss | 6004 | 54 | 5 |

The baseline constructs N full cards even for a miss. The new full-card path
constructs one card for these hits and none for misses; scalar mode constructs
no full cards. Two empty sections among 1,000 owners therefore change from
6,004 SELECTs to 56 for a full-card hit, 54 for a full-card miss, and 5 for either
scalar outcome. Full-card integrity validation uses owner batches of 128;
remaining section queries grow by batch and section, not per owner.

A separate fixture commits 11 owners with 1,000 rows each in separate valid
transactions. An absent-code search previously failed `unsupported` after 36
SELECTs. It now returns empty: 9 SELECTs in full-card mode, 5 in scalar mode.
The unfiltered full-card traversal still refuses its aggregate nested-result
limit, including with `page_size=1`, before reading section payloads.

The eager `select_catalog` entry point uses the same owner batching after its
existing ordered `limit + 1` refusal. For 1,000 complete cards with two empty
sections, its regression permits at most 52 traced statements instead of the
per-owner section-query pattern. All selected scalars and section payloads are
validated before constructing cards; ordering, selection limits and aggregate
nested-result budgets remain unchanged.

## Preserved costs and explicit limits

This is not an index-only or constant-time lookup claim. Catalog-wide scalar
count/byte preflight and streamed semantic validation remain, so filtering does
not hide corrupted Decimal, date, UUID, Boolean or other owner values. Full-card
scans also preserve streamed integrity checks for unrelated section values;
only matching owners consume the nested-result budget. Scalar projections have
no section dependency by design. Full-card page payload is loaded lazily from
the same pinned transaction.

For catalogs without sections the full-card path adds one SELECT (4 → 5) to
separate streamed integrity validation from SQL candidate/page retrieval. Do not
claim universal wall-time improvement from query counts. Local repeated timing
samples were taken on Linux/Python 3.12.14 but were not isolated cross-platform
performance benchmarks; no guaranteed percentage speedup is assigned here.

Legacy v1 JSON storage retains its historical bounded Python filtering/sorting
path, including stable ordering of parseable UUID aliases. v2/v3 SQL comparisons
use explicit Python-backed Decimal, Unicode casefold and UUID collations, never
SQLite numeric coercion or ASCII-only NOCASE. Projection fields, result mode and
request semantics are all continuation-bound.

Regression owners: `tests/test_catalog_scan_optimization.py`, existing
`test_catalog_scan.py`, `test_sqlite_catalog_sections.py`, `test_catalog_queries.py`
and `test_query_parser.py`. The independent 18 new methods cover typed SQL
semantics, paging, corruption, budgets, legacy fallback and hostile projections;
the complete focused set contains 104 methods.
