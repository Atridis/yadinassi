# Declared scalar catalog object forms

`examples/configuration-catalog-forms` is one independently authored XML/BSL
configuration with two different catalog forms, not a fixed Python application:

- **Products:** product title/code, decimal price, Boolean availability, date,
  deletion mark, a BSL discount command and a command opening a Categories card.
- **Categories:** a different layout and a BSL name-normalization command.

Both forms declare `Object` as their main `cfg:CatalogObject.<Owner>` attribute.
Their `Object.<field>` bindings are checked against the catalog schema and lowered
to separate scalar client/server form buffers. The server owns the detached
catalog object; that object and its backend identity never cross the wire.

The host explicitly opts in with `import_catalog_forms_configuration(files)` or
`SQLiteCatalogBackend.create_catalog_forms(path, files)`. Ordinary imports and
inert archives do not acquire execution permission. The application source and
schema must match the activated database before a form lifecycle starts.

Use the configuration UI's explicit `--catalog-objects` option with this source
directory and the created database. Select a catalog, create a card, enter a
unique code and title, and Save. The list updates behind the retained card.
Opening an existing row uses a bounded host-issued opaque key, **not** an invented
native Ref codec. A client form can use `OpenForm` to create another declared card.

The examples deliberately distinguish two refusals: `Form reject` is rejected by
`BeforeWriteAtServer`; `Object reject` passes form preparation but is rejected by
the mandatory object `ПередЗаписью` handler. Products also reject negative prices.
Dirty cards refuse Close until saved. No deletion or bulk-write operation is
implied by selecting rows; the deletion mark is a field saved on one object.

`WriteObject()` is an explicit local host service, not native standard FormWrite
parity. Confirmed writes refresh from the database. An uncertain receipt keeps
the exact original intent locked; refreshing a confirmed write never repeats its
form handler or Write. Other dirty cards keep their buffers and original revision.

This profile intentionally excludes tabular sections, reference fields,
hierarchical catalogs, documents, arbitrary nested paths and CommonModule
OpenForm integration. Unsupported behavior fails admission rather than being
silently ignored. Browser and native parity evidence must be stated separately
from the existence of these examples and local tests.

Source/schema corruption stops the application fail-closed, including normal
receipt recovery calls. Pending intent is not cleared or replayed; repairing an
archive or privileged reconciliation is outside this UI service. The receipt
retry guarantee assumes the same valid source-bound database remains available.

Date fields retain ordinary empty `Date(0)` in the local scalar form-state
packet. This is not new native transfer evidence: generic InvocationPort
arguments/results still reject that endpoint, as do fractional/overflow dates.
The generic browser renderer currently displays dates as read-only ticks.
Date changes through BSL and typed host form events are supported; a browser
calendar/date editor is not provided by this block.

The application wire contract is explicitly `/2`: entries distinguish ordinary
forms and catalog object forms; one selected authoritative catalog projection
contains at most 256 rows and opaque record capabilities. Overflow is refused,
not represented as a complete list. Record capabilities are bounded to 4096
per application and never grant access outside the owning declared entry.
