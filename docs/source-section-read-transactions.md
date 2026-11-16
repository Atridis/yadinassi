# Deferred snapshots for section reads

Owned v6 section read_documents and read_document_bundle now use deferred
SQLite BEGIN rather than BEGIN IMMEDIATE. Reading no longer reserves
SQLite's single writer slot. Pre-open integrity checks and checks inside the
snapshot remain; base document rows and section rows are read within one
transaction. The private transaction flag keeps nested base reads in that
snapshot, and owned reads roll it back on success.

Explicit caller transactions remain untouched on success and are aborted on
failure as before. Writes still use their existing immediate transactions.
No persistent cache, schema, grant or data-validation rule changes.

Tests use a second SQLite connection with timeout zero: a reader permits a
writer reservation, and reads still succeed while another writer holds
uncommitted section changes, observing only committed data. SQL traces verify
deferred BEGIN and owned rollback; corruption tests cover owned and caller
transactions. This does not promise simultaneous write commits under SQLite
rollback journaling, and is not native 1C parity evidence.

Catalog/document write and construction context guards still forbid restarting
an aborted lifecycle transaction. Immediate writes and deferred reads share the
same restart guard; tests cover all four contexts for both read entry points,
including reads inside an already active caller transaction.
