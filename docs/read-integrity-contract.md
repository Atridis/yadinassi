# Read integrity and connection-local leases

A backend still permits one active view or writer. Read views now borrow its
single retained **readonly** SQLite connection, never a writer connection.
Closing a read view ends its transaction and disposes its cursors and tokens.
The idle connection retains no read transaction, so other writers can commit
between operations. Closing the backend physically closes this handle too.
Failed rollback or close keeps the existing poisoned-owner recovery discipline;
a possibly live connection is never returned to the idle slot.

A successful source-validation proof contains only immutable bounded validation
facts and budget totals. It remains attached to the exact connection on which
validation ran. On a later lease, the backend first pins its real read snapshot,
checks its schema/source/database guards and compares that connection's
`PRAGMA main.data_version`. A foreign SQLite commit invalidates all old proofs,
even when configuration generation did not change. Own writer acquisition
conservatively invalidates them too. A new connection always starts cold.
The epoch is never refreshed after rollback: a later commit must not relabel
old validation as proof for new contents. Failed validations publish no proof.

The first validation is still linear in the complete source. Narrow projection
and exact search do not make this cold cost disappear or allow hidden malformed
values to escape validation. Query adapters still charge their specified original
source budgets on every occurrence, including hidden document sections.
Continuation tokens, mutable cards and VM managers never enter the proof cache.

File admission keeps regular-file, size, link and reparse checks and binds the
backend to its observed file identity. A detected replacement fails closed.
This does not claim protection against an adversarial same-user filesystem race
that replaces and restores paths between all observations. Ordinary commits by
other SQLite connections are within the invalidation contract. WAL remains
unsupported; no read operation installs indexes or performs schema maintenance.

Sequential host-thread handoff of an idle readonly connection is permitted;
concurrent operations on one backend remain unsupported. Connection retention
is not a new concurrent-query API or an implicit transaction spanning BSL calls.

## Validation scopes and projections

Catalog source proofs cover the same scalar/owner checks as before. Document
`document-coarse` proofs cover only SQL shape and source byte/count bounds; they
are not scalar or section proofs. `document-record` proves one complete selected
record, including sections and Posted state; `document-full` proves every record
and carries Query's original-source budget totals. A point field getter and
BINARY FindByNumber require coarse plus selected-record validation, not unrelated
full semantic validation. Query and Select require full-source validation.
Only a matching scope can satisfy a later request on the same pinned epoch.

A warm document field read projects the requested header payload without
constructing a partial card. A custom field needs header JSON, not section JSON.
Read/write transaction adapters keep their existing path and never borrow a
readonly proof. Select filters and bounds materialization in SQL but keeps full
detached matching cards, so selection.GetObject still uses that snapshot.
Posted state is joined during source validation/projection, not fetched once per
document. Neither a range nor an unrequested field hides corrupt data within
its original validation scope.

INNER join filtering uses already-bound source-local conjunctions only when
all joins are INNER and the entire WHERE/ON region is proven total. Arithmetic,
OR, outer joins, derived sources and unsupported source families stay on the
existing path. The original WHERE/ON remain residuals, and all original source
integrity/budget checks still run. This is not join reordering or a limit bypass.

Recorder scans merge two ordered streams on the same caller-owned snapshot:
partition revisions (including empty partitions) and movements. Declaration,
FK, row/byte budgets, canonical decoding and exact snapshot hashes remain.
The batch reader never begins, commits or closes the borrowed transaction.
