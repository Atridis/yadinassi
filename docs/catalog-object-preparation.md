# Explicit catalog-object preparation

`prepare_catalog_object(source, receiver, cancel=False)` is a host-only direct
handler bridge. It runs the supplied original `ПередЗаписью` procedure against
an existing disposable `BSLCatalogObject`. Direct catalog field names and
`ЭтотОбъект` refer to that same candidate; ordinary local parameters shadow field
names. Reference arguments retain live field setters. The result is a Boolean
cancellation and a tuple of host `UserMessageRecord` snapshots.

The current profile supports plain routines, branches, row iteration, scalar
expressions, maps, structured messages and reference `ПолучитьОбъект` reads.
Catalog rows expose read-only one-based `НомерСтроки`/`LineNumber`, recalculated
from their current position, never the internal row UUID. Removed rows remain
unavailable. This is local behavior, not measured native parity.

The bridge does not discover or activate imported code. It does not expose
catalog writes, global catalog managers, dynamic execution, I/O constructors or
client/server crossings. Source size, interpreter steps, text production and
message count are bounded. These are execution-profile limits, not a general
sandbox for arbitrary untrusted code. The host remains responsible for selecting
and authorizing exact source and schema identities.

## Write coordinator contract

`write_prepared_catalog_object(source, receiver, cancel=False)` now implements
the bounded host write coordinator. It is not an installed object-module hook,
an importer activation or a renderer command. Ordinary BSL `Write` keeps its
existing behavior. The host explicitly selects the exact source and a disposable
object from an admitted logical schema.

```python
from yadinassi.db.catalog.catalog_object_preparation import (
    CatalogWriteRefused, write_prepared_catalog_object,
)

# source is the host-selected original ObjectModule.bsl text.
# candidate is a disposable CatalogObject with its kind reference and warehouse
# rows already populated. No stored module is selected automatically.
try:
    messages = write_prepared_catalog_object(source, candidate)
except CatalogWriteRefused as refused:
    messages = refused.messages  # No record was written.
```

The writer begins its ordinary transaction and verifies database, generation and
catalog schema before executing the handler. In this route, each reference
`GetObject`/`ПолучитьОбъект` reads from that same writer view. The original kind
and warehouse deletion-mark checks therefore cannot race a separate writer
between validation and commit. Existing SQLite scalar/row reference-existence
checks remain in force; the host does not duplicate or relax them. These
GetObject reads use no separate connection, long-lived reference cache or
temporary global backend swap. Direct reference attribute reads and
`Строка(reference)` are outside this writer profile: their ordinary reader fails
closed with `busy`, rather than reading outside the active transaction. The
original BSL still owns its required-reference, duplicate-row and name
rules. Messages remain inert host records, not navigation instructions.

On ordinary success the same candidate is durably written through the existing
create/update and numbering transaction. Its prepared values are visible
to the caller. Refusal, parser/runtime error or conflict does not report success
and releases the writer. Preparation can still change this disposable candidate
on failure, as in the original preparation-only API; it is not a UI edit-buffer
rollback guarantee.

An unknown outcome leaves the submitted candidate unusable for further
writes. After cleanup, use a fresh object to read the current row. The read
cannot resolve the prior write and never reruns the BSL handler. This boundary
does not admit the original demo form or a tabular editor.

### Preparation-only callers

1. Use a fresh candidate. A receiver with a pending or unknown write is
   rejected before parsing or execution.
2. Obtain a disposable candidate and exact admitted object source for the current
   configuration identity/generation. This API does not make that admission.
3. Prepare once. Cancellation or error is not durable success. Preparation can
   change the candidate even when it fails; discard it and preserve the separate
   editable buffer. There is no implied rollback.
4. After all form/object guards succeed, atomically commit that same candidate
   under backend generation/revision checks. A false cancellation flag is not a
   capability to write. The coordinator must still enforce every write gate.
5. After an unknown outcome, use a fresh read. Never repeat the submitted
   write or BSL preparation to investigate its outcome.

Tests execute the unchanged demo object BSL over a separate explicit logical
SQLite schema, real catalog objects, real references and real tabular rows.
They do not activate the imported demo archive or establish end-to-end GUI/native
acceptance. `test_catalog_object_write` adds actual atomic write/reopen with its
kind and warehouse references and unsaved rows, original refusals, transaction
lock coverage, revision conflicts, both uncertain-COMMIT sides, retained-source
checks and exact retry behavior. No native integration scenario is changed.

The unchanged demo source uses `Формат(НомерСтроки - 1, "ЧГ=0")`; the existing
formatter suppresses numeric zero, so its first-row message field is
`Склады[].Склад`, not `Склады[0].Склад`. The bridge preserves this original BSL
output. Message fields are inert strings, not automatic navigation paths. A
source correction and native check are separate from this change.

The MainDemo product validator reads warehouse references in a batch through
ordinary BSL: `Склады.ВыгрузитьКолонку("Склад")`, followed by a Query selecting
only `Ссылка` and `ПометкаУдаления` with `Ссылка В (&Ссылки)`. The owned
preparation adapter admits that closed shape for same-catalog references
from the same metadata snapshot. It borrows the existing writer, registered
read lease, or form/list read view; it does not activate the general Query
API in a handler. SQLite reads only the reference and deletion mark, using
one parameterized statement unless the connection's bind limit requires more.
The BSL row pass still produces the same messages in row order. This source
change applies to MainDemo; the historical demo fixtures keep their archived
module bytes and reference outputs.
