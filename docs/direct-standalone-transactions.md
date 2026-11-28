# Standalone direct transaction lifecycle

This slice enables canonical transaction controls for an admitted synchronous
standalone direct module over its exact SQLiteDBContext. It does not enable async,
queued-task, configured-application, source-handler, form, or logical-server
transaction control. It reuses the database coordinator, not VM execution.
A managed compilation profile alone neither grants nor removes this standalone
runtime contract. Source-backed catalog writes remain subject to their existing
preparation restrictions. Main_demo source admission may borrow a registered
read-only lease of the exact active writer, validating the unchanged source,
schema, profile and handler grants on that same snapshot. This allows catalogs
with no object handler (for example, Warehouses) to stage ordinary writes. A
policy-selected main_demo BeforeWrite handler uses a separate bounded direct
[preparation lane](direct-transaction-beforewrite-design.md); arbitrary host
preparation and legacy handler execution remain unsupported.

The module owns a fresh private lifecycle object. No database execution token is
installed just for running a module: doing that breaks ordinary server boundaries.
A canonical BeginTransaction, CommitTransaction, RollbackTransaction or status
call lazily enters the existing coordinator scope. Status acquires no writer.
Resolved commit/rollback closes that scope; a later transaction gets a new token.
The scope stays only for an open or uncertain journal. Root exit uses the existing
unclosed-transaction rollback/error and uncertain-commit resolution rules.

Every host boundary checks the lifecycle, exact token and backend identities.
Read/source/schema validation remains in the existing backend; the lifecycle is
not a cached permission or metadata grant. Pending/active scheduler state aborts
before subsequent work. Caller and inherited admission cannot be widened by a
nested call. Imported scalar helpers can share the same root owner; this does not
admit catalog objects owned by another interpreter or bypass source boundaries.
A server crossing during an explicit transaction remains refused before effects.

The original owner is restored only for unwinding its own coordinator after a
host callback corrupts transaction ContextVars. Foreign journals are never
adopted or rolled back by cleanup. An existing uncertain journal may be resolved
only by the coordinator's explicit CommitTransaction recovery, without replay.

Coverage includes source/AST/prepared entry, normal commit/rollback, nested begin,
unclosed and BaseException unwind, token/backend corruption, root reentry,
pending tasks, owner revocation, policy-time service mutation, inherited denial,
server effects, and before/after commit faults including a later-root recovery.
The accepted 14-case period replay now passes with its original explicit extreme-
writer non-parity exclusion unchanged. This is not a claim of complete native
transaction semantics. Broader pre-existing InformationRegisters, imported object
ownership, and configured-application gaps remain separate.

Import initializers retain a narrowed transaction-admission scope. Imported
exported routines may use canonical controls only under the admitted caller's
root owner. Captured canonical control functions keep these same checks; a bound
control belonging to another Interpreter is rejected, even for the same backend.
Execute fragments share the owner. Eval may inspect status, but transaction
controls invoked from Eval are explicitly unsupported in this bounded slice;
this avoids inheriting the older standalone Eval procedure-call discrepancy.

The lifecycle is thread-bound as well as token-bound: a retained boundary cannot
acquire a transaction from a different host thread while the root has no token.
Existing refusal tests now explicitly select a denied caller and retain their
no-coordinator-call assertions. Separate positive tests exercise Begin/write/
Commit inside Execute and preserve the old no-effects behavior under inherited
denial. No snapshot, native fixture or expected observed-query output is changed.


## Source-backed catalog boundary

The previous `busy` occurred before handler selection: `_main_demo_write_source`
opened an independent reader and rejected every active writer, even for a catalog
without an object handler. Only that read ownership is extended. A registered
lease must belong to the current execution token/backend and open UnitOfWork;
checks run before and after source validation. Closing it releases the lease, not
the writer. Unrelated writers, foreign tokens, invalid source/schema and uncertain
journals are not reinterpreted as an absent handler. No source decision is cached
across transaction boundaries. Existing staging, rollback and uncertain-commit
recovery are unchanged.

Selected main_demo BeforeWrite handlers now have a separate direct-only lane,
with owner/context/thread checks, a readonly writer lease and a savepoint. The
prepared draft is frozen before staging; cancellation and faults do not create
journal entries, and uncertain recovery never re-executes the handler. See the
[contract and regression matrix](direct-transaction-beforewrite-design.md).
This does not admit arbitrary host-supplied source or legacy handler execution.
