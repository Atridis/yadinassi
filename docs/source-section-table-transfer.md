# Bounded source document section Load / Unload

`Unload()` / `Выгрузить()` returns a detached, typed ValueTable snapshot of all
section fields, in their declared order. Every row must have all fields assigned.
The existing bounded query-snapshot representation preserves scalar qualifiers
and source-owned enum/catalog/document reference identities. It can be read,
existing cells can be changed within that snapshot contract, and it can be used
as an external source query table. It is not a general editable table factory:
new-row defaults, reference coercion and arbitrary nullable schema mutations
remain restricted by the existing snapshot implementation.

`Load(table)` / `Загрузить(таблица)` requires an exact ValueTable with every field
column exactly once, matched case-insensitively. Extra/missing columns, foreign
reference metadata, Null/Undefined and values failing the section's exact codec
are refused. There is no coercion, inferred default or partial-column mode.
Rows and the total owner's section buffer are bounded before replacement.
Only a successful replacement invalidates old row handles and advances the
iteration version; failure leaves the old buffer intact. The section handle
itself remains valid. Loading does not write the database or run ObjectModule
handlers; explicit document Write is still required for persistence.

Owner, lifecycle, safe-mode and synchronous access checks are retained. No new
SQLite profile, migration, transaction admission or native parity claim is added.
