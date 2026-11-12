# Prepared configuration admission

Source-granted SQLite application backends retain one successfully admitted,
immutable source import for their lifetime. Repeated catalog/document reads,
source export and preparation can reuse it instead of reparsing XML and
recompiling form modules on every access.

This is **not** a data-row cache, a shared execution context or permission to
skip database validation. Each operation still establishes its own SQLite
snapshot, reads and bounds the actual configuration inventory, recomputes
hashes from its bytes, and checks the exact profile, database identity,
configuration generation, schema and stored metadata. A matching filename,
persisted digest, profile marker or generation alone cannot authorize reuse.
External changes at an unchanged generation must still be rejected.

The positive result is owned by one backend, not shared globally. The key
includes the complete checked source inventory and database/profile/schema
binding. The cache stores frozen metadata, source bytes and immutable handler
identities, not interpreter state, form instances or mutable syntax trees.
Only a fully admitted candidate is retained; failures and interruptions are
not cached. The first positive binding cannot be replaced by a different
candidate in that backend. Closing releases the retained entry; reopening
performs fresh admission.

Supported existing paths are catalog/application forms, non-posting document
forms, mixed business/reference applications, and the closed physical-13
posting variants, scalar accumulation format 14 and reference inventory core
format 15, including the separately source-granted full inventory form variant.
Posting/accumulation recorder/schema/row checks still run as required;
reusing the full form variant never substitutes its core projection for the
original source. Other source/storage profiles retain their existing paths.
There is no new source grant, profile conversion, migration, long-lived
observer connection or `PRAGMA data_version` shortcut. The inventory form
variant retains its complete original source and immutable command/report
grants. Its temporary core projection cannot occupy a full-variant entry; the
original core creator still refuses the form variant.

Receipt lookup, uncertain commit handling and handler execution are unchanged.
Prepared admission does not replay actions or establish that an unknown
operation rolled back. It also does not retain application source across a
host restart.

Regression coverage uses deterministic import/compiler call counts, not
machine-specific latency thresholds. It checks repeated scalar reads and
exports plus unchanged-generation tampering, profile/schema changes,
independent backends, failed/interrupted admission and the exact full posting
source grant.

## Stock read admission

Repeated read/write beginnings in the existing accumulation profiles reuse only
the frozen XML import. Actual stored bytes are read, bounded and SHA-256 hashed
inside every current snapshot. The key includes the complete path/kind/size/hash
inventory, application/storage/schema versions, database and configuration
identity, exact profile marker and source digest, and catalog/document schemas.
Register fields and recorder membership are compared by the live movement port
even on a hit. Full row validation on open and explicit validation requests is
unchanged. Closing or explicitly clearing the entry makes the next owner cold.
Changed bytes or metadata cannot reuse an old admission; a failed candidate
does not replace the first positive entry, so repair can safely recover it.

This does not cache movement rows, read-validation proofs, query results,
transactions, compiled mutable programs or handler execution. In particular,
read leases retain their existing lifetime and staged/committed/rolled-back
stock remains visible only through the original transaction authority.
Deterministic importer call counts cover a 23-snapshot sequence; they are not
an end-to-end UI latency claim.
