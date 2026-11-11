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
