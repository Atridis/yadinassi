# Independent information registers

This is an authored, bounded local application contract. It does not claim
native method parity. This page describes independent, nonperiodic information registers.
[Periodic registers](periodic-information-registers.md) use a separate explicit v9 contract. Registers use separate tables and typed composite dimension keys,
not catalog or document records.

## Configuration and storage

A configuration declares `InformationRegister` names and supplies
`InformationRegisters/<Name>.xml`. Properties must explicitly set
`InformationRegisterPeriodicity` to `Nonperiodical` and `WriteMode` to
`Independent`. Child `Dimension`, `Resource` and `Attribute` objects use the
same closed scalar qualifiers and catalog-reference fields as catalogs.
There must be 1–16 dimensions, at least one resource, and at most 64 total
fields. Metadata IDs must be unique across the configuration. Unknown behavior,
modules and unsupported metadata remain inactive; this block does not execute
configuration code.

New configurations containing registers explicitly create SQLite version 8.
Catalog and non-posting document storage retain their existing contracts.
Opening versions 1–7 never upgrades them or silently introduces registers.
Version 8 supports register-only and mixed catalog/document/register databases.
Public record identities are the ordered, typed dimension tuple. Strings are
case-sensitive; number qualifiers normalize numeric representations before key
encoding. Catalog references retain database and target metadata identity.

## Record manager

`InformationRegisters.<Name>.CreateRecordManager()` returns a detached buffer.
Assign dimensions, resources and attributes; `Write()` inserts a missing key.
To update an existing key, call `Read()` first. `Selected()` reports whether the
buffer has a persisted revision. Reading a missing key preserves its dimensions
and resets resources/attributes to defaults. `Delete()` requires a selected
record. `Clear()` resets the buffer. Dimensions of a selected record cannot be
changed until `Clear()`; there is no implicit key rename.

`Get(Structure)` requires all dimensions and returns a Structure of resources
and attributes, with default values when absent. `Select([Structure])` admits
only dimension equality filters and returns a detached selection with `Next()`.
At most 1000 selected rows are returned; overflow is an error rather than silent
truncation. Ordering is deterministic local key order, not native collation.

```bsl
R = InformationRegisters.Prices.CreateRecordManager();
R.Item = "A";
R.Region = "North";
R.Read();
R.Price = 12.50;
R.Enabled = True;
R.Write();
Message(InformationRegisters.Prices.Get(
    New Structure("Item,Region", "A", "North")).Price);
```

## Record sets and filtered replacement

`CreateRecordSet()` exposes `Filter.<Dimension>.Set(value)`, `Add()`, `Get(index)`,
`Count()`, `Clear()`, iteration, `Read()` and `Write([Replace])`. Rows have typed
field properties. Added rows inherit active filter values. Filter changes
require an empty buffer. Removed row objects cannot mutate a new buffer.

`Write()` replaces only the active filter scope, atomically. Every submitted
row must satisfy that scope, and duplicate dimension keys are rejected before
modification. An empty set deletes the selected scope. `Write(False)` appends
and rejects existing keys without partially inserting other rows. Unfiltered
replacement requires `Read()` first; an unfiltered blind replacement is rejected.
`Clear()` empties rows but retains the observed snapshot and filter, so
`Read(); Clear(); Write()` explicitly deletes the observed whole scope.

A successful `Read()` captures a scope revision digest. A subsequent write
rejects intervening changes in that scope instead of overwriting stale data.
Filtered writes without `Read()` explicitly replace the current matching scope.
Changes outside the filter do not invalidate the observed scope.

```bsl
S = InformationRegisters.Prices.CreateRecordSet();
S.Filter.Region.Set("North");
Row = S.Add();
Row.Item = "B";
Row.Price = 19;
Row.Enabled = True;
S.Write(); // Replaces North only; other regions remain unchanged.
S.Read();
For Each Row In S Do
    Message(Row.Item);
EndDo;
```

## Transactions, ownership and limits

Each write uses one owned SQLite transaction, a frozen intent and a durable
receipt. Record revisions are monotonically allocated per register, preventing
stale writes after delete/reinsert cycles. Record sets replace their entire
scope in one savepoint; failed validation, duplicate keys or limits leave the
previous scope intact. If commit acknowledgement is lost, buffers freeze until
the same write resolves its exact receipt. Receipts from catalog, document and
register operations cannot reuse operation identities.

Read-only connections reject all writes. A backend permits only one active
read/write view, and mixed query sources share that same pinned snapshot.
Register source data is bounded to 10,000 records and 16 MiB per register,
1 MiB per record/intent, 1000 rows per record set or ordinary selection.
Malformed stored values, foreign keys, stale metadata and unsupported layouts
fail closed. Native codecs, dynamic `New` and `TypeDescription` do not admit
these database-bound dynamic objects.

Within this nonperiodic v8 profile, periodicity and virtual slices remain excluded;
see the separate v9 contract above. Recorder-subordinate registers, posting/movements,
indexes and distributed transactions are outside this block. Query support is
documented with the query engine's supported source profile.
