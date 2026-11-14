# Batched source document section validation

Source v6 document selection previously issued two section queries per selected
document, even though the section payloads were only being validated. It now
uses one bounded ordered payload query for the selected document family (or one
explicit identity). Global storage preflight remains in place; this does not
remove the schema, UUID, byte/count or transaction checks.

Each record still must have exactly its declared section inventory. Every payload
is decoded and re-encoded canonically, with per-section limits plus aggregate
per-document row/byte limits. Missing, foreign and malformed sections fail rather
than being filtered away. The database selection and section validation occur in
one existing transaction snapshot; a failed read still aborts that transaction.
The implementation streams records and keeps only the current decoded section,
not a second copy of all sections. GetObject/OnRead and write paths are unchanged.

This reduces round trips, not the required validation work: all selected data
is still inspected. It is not an unbounded query mode or native parity claim.

Local paired SQLite trace on 32 one-section documents: section SELECTs 70 -> 7,
all SQL statements 121 -> 58, including unchanged global preflight. The previous
64 per-document count/payload queries become one batch query. This is a query
count measurement, not an elapsed-time or throughput claim.
