# Typed references in a configuration application

Development checkpoint, not a completed acceptance claim. This separate source
profile adds single-target CatalogRef fields to catalogs, document headers and
scalar document sections in the owned application host. Historical scalar
profiles do not acquire reference admission or profile-conversion authority.

The authored example extends the mixed application with Products.Category,
Orders.Category and Orders.Lines.Product. Server form state retains real typed
catalog references. A client replica receives an issued form-scoped identity,
presentation and empty marker, never a record UUID or server reader. This is a
private form transport, not native managed-form or generic invocation parity.

Choice uses existing non-deleted records, bounded exact-code filtering, explicit
overflow and one-shot owned tickets. Cancel preserves the previous value; Clear
assigns the typed empty reference. A removed row or replaced form cannot receive
a late result. Pending writes/refresh recovery do not permit a new selection.
Unknown outcomes lock rather than replay writes or pretend to cancel an action.

The profile creates a new v7 database explicitly with
`SQLiteCatalogBackend.create_reference_application(path, files)` and launches
with `--reference-application --f existing.sqlite`. Existing source bytes and
schema stay pinned at creation, reopen, transactions and export. No automatic
migration, DocumentRef, composite types, creation inside the picker, hierarchy,
posting/movements or new transaction authority is enabled. Client UUID/GetObject
and arbitrary reference assignment remain explicitly unavailable.

The initial 34 Python contracts have been authored but not executed at this
checkpoint. Browser integration and final validation are still in progress.
