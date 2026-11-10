# Reference Orders workspace

This separate, opt-in application exercises a complete business flow: Orders
list → create/edit one order → choose customer or a selected line's product in
an owned child form → resume owner → save → reopen exact typed references.
It is a catalog-backed example, not document storage or native `OpenForm` parity.

## Start with a separate database

```sh
python -m yadinassi --create-db reference-orders.sqlite --import-xml examples/forms/reference-order/configuration
python -m yadinassi.ui.reference_orders_workspace examples/forms --f reference-orders.sqlite --open-browser
# Installed package entry point:
yadinassi-reference-orders examples/forms --f reference-orders.sqlite --open-browser
```

The configuration defines Customers, Products with UnitPrice, Orders with
Customer and Total, and Lines with Product, ItemDescription, Quantity, Price and
Amount. Customer and Product are typed catalog-reference fields stored as exact
CatalogKeys, not names, codes or browser row numbers. Existing Orders databases,
profiles, launchers and workbench behavior remain unchanged. There is no migration
and no document-v7 dependency. Database creation refuses an existing destination.
The launcher only opens an existing database and validates this fixed schema.

The new database is initially empty. Add Customers and Products with the existing
BSL catalog API before opening a choice. For example, save this trusted local
script as `reference-seed.bsl`, then run
`python -m yadinassi --f reference-orders.sqlite reference-seed.bsl` once:

```bsl
C = Catalogs.Customers.CreateItem();
C.Code = "C001";
C.Description = "Example customer";
C.Write();
P = Catalogs.Products.CreateItem();
P.Code = "P001";
P.Description = "Example product";
P.UnitPrice = 2.50;
P.Write();
```

Use New order, enter its code and description, and Choose customer. Select a
result row and Choose, or Cancel to retain the current reference. Add a line,
select that exact line, then Choose product. Choosing a product copies its current
description and unit price into editable line fields. Adjust quantity and price,
recalculate and save. Return to Orders, refresh the list, and reopen the record.
Changing the editable order code never changes which stored record is updated.

One owner and at most one child can exist at a time. While a child exists, the
owner's editing, saving, closing and other choices are blocked by the workspace
and server, not just by a visual overlay. Choose, Cancel and ordinary child Close
return a closed child snapshot. The server applies the result to the owner before
retiring the child. The renderer then refreshes the ordinary owner snapshot and
keeps the owner blocked until that refresh completes. Cancel never writes and
preserves the current references and drafts. Dirty owners require Save or
Discard / Reload before closing; discarding a new order creates a clean draft
without writing. Workspace close requires all forms to be closed first.

## Identity, limits and recovery

The fixed `yadinassi-reference-orders/1` protocol exposes only `workspace.hello`,
`workspace.list`, `workspace.open`, `workspace.form`, and `workspace.close`.
Every outer result has exactly protocol, state, error, session and form. There
is no unsolicited update channel. Session descriptors have exactly id, kind and
owner; an order has owner null and a choice points to its order's opaque ID.
Regular form requests remain `yadinassi-form-ui/1`, with ordinary `form.hello`,
`form.snapshot` and `form.event` operations. The browser cannot select package
paths, catalog targets, routines, endpoints, callback names or CatalogKeys.

Order and choice lists are live-record snapshots of at most 32 rows, with an
optional exact-code filter. Truncation is explicit. Server-only mappings bind
opaque displayed rows to exact typed keys. Duplicate display names never select
an identity. Search replaces that mapping and old row IDs cannot be reused.
A one-shot server capability binds the choice to its owner generation, monotonically
issued choice serial, catalog target and exact live owner row ID. Selection is
rechecked for catalog, database, existence and deletion at application and again
at save. The fixed, host-only zero-argument ApplyChoice endpoint is not a browser
or client BSL binding. The single-form launcher rejects both workspace-only
application selectors rather than bypassing the owner broker.

There are at most two live sessions and 256 lifetime session allocations per
launch. Session IDs are never reused; open request tokens are deduplicated and
cannot be reused for another intent. Stale list revisions cannot open a different
row. Scalar form limits and complete-projection admission remain in force.
All reference keys and detached objects live only in the server process; no read
transaction remains open between actions.

Save uses the existing workbench's immutable target, original optimistic revision,
whole header/line projection and retained write-receipt recovery. A concurrent
writer produces a conflict without silently overwriting or retargeting. A
confirmed commit followed by a failed refresh permits only Refresh saved record,
not another write. A database write with an uncertain outcome over a healthy
channel retains its exact intent for explicit Resolve save outcome.

Unknown transport, malformed replies, an installation fault after selection
admission, or uncertain child cleanup locks the whole workspace. There is no
automatic replay, reconnect, invented rollback, or claim that old values survived
an ambiguous installation. Stop and reconcile the database separately if the
transport is lost. Process teardown closes resources without applying unfinished
choices; teardown is not proof that a previously attempted save rolled back.

The dedicated Python regressions cover typed-key readback, create/reopen,
selection ownership, cancellation, stale rows, cross-catalog/database injection,
preflight and post-install faults, conflicts and write recovery. Separate renderer
and browser checks cover owner blocking and refresh. Test definitions are not
execution evidence: record the checked source commit and actual suite results.
No new real-1C managed-form observation or parity is claimed by this application.
