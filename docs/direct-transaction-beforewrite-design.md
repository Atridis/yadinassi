# Research: selected BeforeWrite inside an explicit transaction

Status: local candidate with original-root witness; final review and aggregate
checks required before integration. Design baseline: published `35708136`.

## Original-root ingress proof

The initial prototype admitted `copy_context().run(card.write)` when the new
handler scope was created inside the copied context. That was a blocker despite
passing handler-local checks. The candidate now creates a private root witness
in `python_direct_transactions.execution`, before any transaction service. Its
ContextVar token can be reset only in the original Context; rotating it proves
that identity without executing external code. The witness also pins thread,
active interpreter, exact database context and scheduler, family identity and
generation, profile and client/module context. Closed/released, asynchronous,
configured, safe-mode and source-transaction contexts are rejected.

Catalog write ingress checks a present root witness before capability/source
lookup. Canonical transaction controls check it before opening a writer. A
retained witness cannot reactivate after root exit. The handler lane requires
that exact witness and current owned transaction before its savepoint or
preparation lease; an ambient `tx.current` token cannot mint authority. Existing
host-only coordinator calls retain their prior unsupported handler result;
the previously admitted readonly source-policy lookup alone grants no handler
capability. No-handler host behavior remains separate and unchanged.

Tests reject copied-context and foreign-thread entry before capabilities/leases,
copied-context Begin before writer acquisition, stale post-root entry, replaced
scheduler/database/family/profile/context and inherited denial/pending work.
Actual separate direct roots exercise uncertain-commit resolution without
re-running the handler. The old reproducer is retained as a denial regression.


## Existing evidence

* Source admission can now read a verified main_demo snapshot through an exact
  registered lease of the current UnitOfWork. Absence of a handler is established
  only after the unchanged manifest/profile/schema checks.
* `CatalogObject._write` selects the backend policy before it stages a draft.
  Handler-bearing drafts require the separately guarded preparation lane.
* `Transaction.savepoint` covers participant registration and the UnitOfWork
  requests/results/bindings/receipt mutations. It preserves earlier root stages
  when one operation fails. This is the intended SQL rollback boundary.
* `Transaction.commit` builds acceptance images before durable commit. Resolution
  uses the frozen UnitOfWork requests and results, not `Write` or source execution.
* The direct BeforeWrite adapter already allows only bounded receiver edits,
  exact reference reads, local maps and captured user-message records. It has no
  persistence or transaction-control endpoint. The explicit-transaction lane adds
  pinned scope/owner checks to its existing lifetime guard.
* The original Products handler trims Description, validates referenced Kind and
  Warehouses with GetObject, detects duplicates, and returns cancellation/messages.
  Reads therefore must see earlier stages of the same root transaction.

## Finite candidate lane

1. Require an exact current open SQLite transaction, direct execution policy,
   main_demo profile and a nonempty handler source actually selected by current
   backend policy. Do not admit arbitrary host-supplied preparation when the
   catalog has no source grant. Preserve existing source equality checks.
2. Enter the existing transaction savepoint before preparation. Pin transaction,
   execution token/backend, thread, manager/schema/receiver and source identities.
3. Issue a registered readonly lease from that same UnitOfWork. Validate it before
   use, at every handler boundary, after source execution and before closing.
   The handler gets this readonly view, never UnitOfWork or a writable port.
   Its nested invocation cannot widen transaction admission.
4. Execute only the existing bounded generated BeforeWrite adapter. No VM,
   fallback, configuration session, arbitrary callbacks, database writes or
   Begin/Commit/Rollback are introduced. Check owner and authority after any host
   boundary, not just before an argument or method is resolved.
5. On cancellation, raise the existing CatalogWriteRefused with message snapshots.
   Close the lease and unwind the savepoint. No draft or receipt is staged.
   As in the existing disposable-candidate API, buffer edits are not silently
   described as rolled back; SQL state and journal entries are the atomic scope.
6. Revalidate the selected source on the same writer snapshot; require unchanged
   manager/schema/owner/target. Close the lease before staging. Freeze the fully
   prepared draft including sections; stage exactly once using the existing
   Transaction.stage path. A second write of the pending object remains refused.
7. Commit and uncertain resolution remain untouched. Never call the handler or
   source preparation to resolve an already submitted journal. A definitely
   rolled-back operation may be explicitly retried by the caller as a new intent.

## Regression coverage and verification requirements

- Original handler create/update commit and rollback, whitespace normalization,
  duplicate references, deletion-mark checks, cancellation message snapshots.
- Handler reads see earlier staged reference changes; a failed handler does not
  erase unrelated earlier stages when caught, and root rollback erases all stages.
- Every source/schema/grant mutation is rejected, never treated as no handler.
  Host-supplied mismatched/ungranted source and fixed-profile violations fail
  before candidate effects or staging.
- No separate connection, writer close, implicit commit, VM dispatch or recursive
  persistence endpoint. Exact lease/token/backend/thread and receiver ownership
  survive argument effects, reentry, copied context and late authority changes.
- Exceptions, BaseException, cancellation and failed staging leave no leaked lease
  or orphan receipt. Savepoint failure preserves a fail-closed transaction state.
- Before/after COMMIT transport faults and later-root resolution prove exactly one
  handler invocation and retain the original frozen submitted draft.
- Legacy explicit-transaction/source APIs are unchanged unless separately tested
  and intentionally approved. No broad promise of native transaction parity.

## Originating catalog family

The direct root captures its already-created exact catalog family and metadata
identity at activation. Handler admission requires both the live root family and
the receiver manager family to be that original family. A different family on
the same backend is not authority, and replacing the root family cannot grant it.
The check neither creates catalogs lazily nor changes standalone host no-handler
behavior. It runs before savepoint acquisition and repeats at handler boundaries.
