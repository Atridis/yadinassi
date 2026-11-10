# Explicit synchronous database transactions

This is a bounded local v11 application contract, not a claim of measured native
transaction parity. The host must explicitly migrate the database using the
existing reviewed migration plan. `BeginTransaction()` never upgrades a file.

`BeginTransaction()`, `CommitTransaction()` and `RollbackTransaction()` (and
`НачатьТранзакцию`, `ЗафиксироватьТранзакцию`, `ОтменитьТранзакцию`) delimit one
synchronous execution. Writes of catalog objects, non-posting documents,
independent register record managers and record sets stage into the same owned
SQLite transaction. The host journal's operation and byte budgets still apply.
Standalone `Write()` retains its existing behavior.

A staged object remains new, and keeps its old revision/number/reference state,
until the entire batch commits. User field and section edits remain in memory
on rollback. Staged buffers cannot be changed, read again, cleared or submitted
again. Each identity can be staged once (one mutation per register). New objects
that must be referenced by another staged object need explicit nonempty refs via
`SetNewObjectRef` before staging.

Before COMMIT, all outcomes are validated and all acceptance dictionaries,
references and operation UUIDs are prepared. After COMMIT the prepared images
are installed without invoking user code. A lost commit response retains the
whole batch, and a repeated commit resolves its root receipt rather than
replaying writes. Rollback cannot claim that a committed batch was undone.

Queries borrow a read-only lease on the owning connection and can see staged
rows. Closing the query closes only its lease/cursors. An outstanding lease
blocks further staging and commit. No snapshot validation cache is shared with
the writer. Direct manager/object/record reads during an active transaction are
currently refused rather than returning a provisional revision as persistent.

The first profile intentionally rejects nested transactions, async tasks and
Await, callback dispatch and transfer to a new server activation. An unfinished
transaction is rolled back when execution ends; an unresolved durable outcome
keeps participant buffers locked until receipt resolution. Catalog object-form
preparation handlers are not yet admitted to the explicit batch writer.
