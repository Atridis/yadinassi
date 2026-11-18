# Standalone direct transaction lifecycle

This slice enables canonical transaction controls for an admitted synchronous
standalone direct module over its exact SQLiteDBContext. It does not enable async,
queued-task, configured-application, source-handler, form, or logical-server
transaction control. It reuses the database coordinator, not VM execution.
A managed compilation profile alone neither grants nor removes this standalone
runtime contract. Source-backed catalog writes remain subject to their existing
preparation restrictions: for example, main_demo catalog preparation can reject
an explicit active transaction as busy. This slice does not certify those writes
or bypass their source validation.

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
