# SQLite writes and unknown commit outcomes

A successful write returns the revision and other results from the transaction.
The logical rows, sequences, document posting state and register movements
commit together. Updates still compare the record revision supplied by the
caller. Explicit transactions retain their savepoint and all-or-nothing rules.

If SQLite does not confirm COMMIT, the caller receives an unknown outcome.
The original write buffer cannot save again. Release transaction resources
and read the current record with a fresh object, or discard and reopen a form.
A fresh read shows what is stored now; it cannot establish whether a particular
unconfirmed operation succeeded. Neither cleanup nor reading invokes a write
or a posting handler. Once COMMIT is confirmed, a failed form refresh can
be repeated as a read only.

Business writes have no receipt tables, durable operation log, resolver or
automatic replay. Opening a database does not migrate it. Do not modify an
existing database to make it open: any storage conversion is an explicit
maintenance operation on an owned, verified copy. Migration proof, source
authentication and inventory movements of type Receipt are separate concepts.
