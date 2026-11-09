# Continuous Orders workspace

Run the fixed Orders intake and existing-record editor together, without stopping
Python between records:

```sh
python -m yadinassi --create-db orders.sqlite --import-xml examples/forms/order-intake/configuration
python -m yadinassi.ui.orders_workspace examples/forms --f orders.sqlite --open-browser
```

Database creation is an explicit separate operation. The workspace never creates
or migrates a database. Its package root is a trusted host argument, not browser
input. Only the fixed `order-intake` and `order-editor` children are admitted.

Choose New order, or Open order beside a listed record. Up to four live forms are
retained. Switch between the list and form tabs without saving, validating or
flushing pending text. Invalid decimal text and focus stay with the owning form.
Save the order using its ordinary command, return to Orders and explicitly
refresh the list. The list is a bounded snapshot of at most 32 records, optionally
filtered by exact code, not a live subscription.

For an existing order, Discard / Reload explicitly abandons local drafts and
reloads the same stored identity. For a new order, Discard new order explicitly
abandons the form only before any save attempt. Once an intake save was attempted,
the one-attempt policy is unchanged: a failed or unknown save must be reconciled
independently, never retried by discarding and replaying the form.

Close form runs that form's ordinary close handler. Dirty or unresolved forms
cannot disappear. Closing a clean tab leaves every other form and the listener
alive. Close all form tabs before Close workspace. Browser navigation guards
include hidden tabs, raw drafts, dirty forms and pending requests. Host Ctrl+C
remains teardown, not proof of database rollback or safe discard.

## Boundaries and guarantees

The separate `yadinassi-orders-workspace/1` envelope qualifies every request and
response with a host-issued form identity. Core replication remains
`yadinassi-form/1`; package versions 0/1/2 and the single-form launcher stay
unchanged. The trusted fixed intake supplies explicit Dirty metadata without
claiming the existing-order application selector.

One owned child process contains independent replica servers and database
contexts. The parent owns independent logical clients. Each editor retains its
own detached object, original revision, storage-line identities and pending write
intent. Selection is resolved through the child-owned list mapping. Browser
requests contain neither backend keys nor package paths, code or procedure names.
The editable order code never selects a save target. Two editors of one record
conflict using their original revisions instead of silently overwriting.

Opening is bounded and operation-token deduplicated. A stale list revision cannot
open a newer selection accidentally. Session identities are never reused, even
after an unsuccessful open. There are at most four live editors and 256 allocated
sessions/open operations per launch. Complete record projection is admitted before
an editor is published. Failed opening cleans its newly owned context and leaves
existing editors intact.

A lost or malformed child transport is workspace-wide uncertainty: all forms
lock, and no reconnect or replay is offered. Database uncertainty over a healthy
transport remains scoped to the owning editor and keeps the workbench's explicit
Resolve save outcome / Refresh saved record behavior. A confirmed write followed
by failed refresh remains refresh-only. See [the workbench guide](order-workbench.md)
for exact recovery semantics and [the form guide](form-app.md) for loopback HTTP,
capability, frame-size and owned-process security boundaries.

No crash-persistent drafts, migration, generic references, arbitrary packages,
conflict merging, transport reconnect, or new native UI parity are claimed.
Verification outcomes must identify the actual source commit; tests existing in
the repository do not establish that they ran.
