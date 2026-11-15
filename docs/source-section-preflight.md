# Single-scan section storage preflight

The v6 section store's verify_extra preflight previously issued two full-table
aggregate SELECTs: one for invalid storage types/byte lengths, and one for
section count and aggregate payload size. It now computes all three counters
in one aggregate SELECT. This path is used repeatedly by ordinary reads and
writes, not only opening a database.

Malformed storage still raises before aggregate overflow. Identity TEXT type
and 36-byte length, payload TEXT type and 262144-byte limit, 160000 total
sections and 16777216 aggregate bytes are unchanged. Empty tables coalesce
both sums to zero. No row is filtered out of the aggregate. Existing superclass,
schema, canonical decoding, ownership and transaction checks are unchanged.

Focused tests exercise empty/populated scans, each identity type/length,
UTF-8 byte lengths, payload and real 16 MiB aggregate boundaries. A mock tests
the 160000 row boundary and error precedence without creating 160k fixtures.
This reduces section aggregate SELECTs from two to one per preflight; it does
not claim a measured wall-clock speedup or new native 1C parity.
