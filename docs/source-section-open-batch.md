# Batched complete section validation at open/update

Complete source v6 record validation now collects bounded document identities
and validates sections once per populated document family, rather than issuing
two section queries per document. This path is used by reopen and source-update
preflight. Scalar/catalog/constant validation still runs first; the foreign-key
check still runs last, including stores with no document records.

All families with records are checked, including those declaring zero sections.
The shared batch validator retains exact section inventory, canonical decoding,
per-section limits and aggregate per-document row/byte limits. Missing sections,
foreign or malformed records cannot be silently skipped. The extra identity scan
is explicitly limited to the existing maximum record count plus one and rejects
an excess count. Existing callers own the transaction; validation neither
commits nor starts a replacement transaction.

No formats, write semantics, source-update eligibility or public capabilities
change. This is query batching, not a claim of native parity or removal of full
integrity validation.

Paired local SQLite trace of `validate_records()` on 32 documents from one
section-bearing family: section SQL 64 -> 1, total SQL 68 -> 5. These counts
cover validation itself, not the surrounding reopen/source import statements,
and are not a timing claim.
