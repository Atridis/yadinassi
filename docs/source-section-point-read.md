# Bounded point section reads

Single-document Read/GetObject and post-write section validation fetch the
declared section inventory plus one sentinel row in one ordered SQL query.
The previous aggregate count/byte query is removed. Each point operation now
uses one targeted section SELECT rather than two.

An extra or missing section still fails, including records whose schema has
zero sections. Aggregate byte/row bounds, exact section UUID inventory and
canonical field decoding are unchanged. The caller retains its transaction
snapshot and rollback-on-error behavior. The sentinel limit bounds rows
materialized even when the store is corrupt; the existing global storage
preflight still validates payload types, per-payload byte bounds and totals.

This does not cache data, relax validation, add capabilities or change BSL
semantics. Source v6 tests cover read/write trace counts, missing/unknown/extra
inventory, noncanonical payloads, row/byte bounds and outer transaction handling.
It is not new evidence of native 1C parity.
