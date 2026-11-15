# Source record preflight scan consolidation

Catalog and document storage verification now gathers malformed-row count,
record count, maximum payload bytes, and total payload bytes in one aggregate
scan per record table instead of two. This also applies to the inherited v6
section profile. Empty tables preserve zero-valued aggregate results.

Existing type, UTF-8 byte-length, revision, database-size, schema-binding,
10,000 record and 16 MiB aggregate payload bounds remain unchanged. Error
precedence remains malformed rows, database size, schema binding, then aggregate
record bounds. No row filtering, persistent caching, schema change, transaction
ownership change or capability relaxation is introduced.

SQL trace tests verify one scan for empty and populated tables. Corruption tests
cover SQLite value types, multibyte values, revision bounds, payload and aggregate
byte boundaries, row-count boundaries and error priority. This is a scan-count
improvement, not a measured wall-clock speedup or native 1C parity claim.
