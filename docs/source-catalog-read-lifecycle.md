# Bounded source catalog OnRead

Catalog ObjectModule `OnRead()` / `ПриЧтении()` is admitted as one synchronous,
zero-argument procedure (the two aliases cannot both be declared). It runs after
persisted fields are loaded by reference/selection `GetObject()` or object
`Read()`. New object module initialization precedes loaded fields; existing
object module variables survive a successful reread. Creation, lookup and query
do not invoke this event.

The read owns a transaction only when no explicit caller transaction exists.
The initialized object, loaded fields and handler share that transaction.
Failures roll back the active transaction and close the failed object; partial
module state is not reusable. Field edits are memory-only, with no automatic
save. Catalog writes during this catalog read and document writes inside the
shared read frame are deliberately unsupported.

Catalog and document reads share a maximum 32-deep recursion frontier and deny
same-record reentry across either family. After any nested operation aborts the
transaction, catching its exception cannot reopen a transaction or continue
catalog/constant/document/query access from that frame. Owner, safe-mode and
synchronous-server admission still apply.

No stored format or automatic migration is introduced. Existing admitted
schemas are unchanged. A catalog previously rejected because of OnRead is a
newly supported definition: an existing scratch database with that definition
absent still requires the normal explicit source-update/new-scratch path, not
silent admission on reopen. This is not full native 1C event parity.
