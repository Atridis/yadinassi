# Database entrypoints and retention audit

This map describes the code at the bounded-read audit checkpoint. It is not a
new profile grant, migration mechanism, or statement of native 1C parity.

## Entrypoints and explicit grants (A3)

| Entry | Admission | What it does not grant |
| --- | --- | --- |
| `SQLiteDBContext(path)` / `SQLiteCatalogBackend(path)` | Existing exact SQLite format/schema and source checks | Opening does not execute configuration modules |
| `SQLiteDBContext.create` | Imported configuration, activation flag (defaults to True) | Unsupported metadata is not activated by copying XML |
| `create_posting`, `create_accumulation` | Exact canonical posting/accumulation configuration | Existing ordinary DB is not upgraded; table presence is not a grant |
| `create_inventory`, `create_inventory_enum` | Separate typed-reference / enum profiles | Core data capability is not a full application/form grant |
| `create_inventory_application`, `create_inventory_enum_application`, `create_main_demo` | Exact full-source profile type, source digest, canonical schema | No arbitrary source, generic migration, or Enterprise compatibility |
| `SourceConstantStore.create/reopen/load_source/update_source` | Separate scratch DB schema, file identity, source/codec binding | Not the numbered ordinary SQLite backend formats; source load does not run startup |
| `SQLiteCatalogBackend.launch_snapshot` | One admitted read snapshot, canonical source and schemas | Returns detached launch input, not activation, writable data or running VM |
| `begin_unit_of_work` / `resolve_unit_of_work` | Existing formats 11–16, ordinary write/read admission | Does not give BSL ownership, form dispatch or arbitrary callback authority |
| `database_transactions.begin/commit/rollback` | Admission token and current synchronous execution owner | No detached/foreign owner or automatic source-profile widening |
| `database_transactions.require_host_root` | Exact v13 PostingApplicationConfiguration, canonical source, no BSL execution owner | Not the generic root for accumulation or arbitrary source applications; specialized roots retain their own admission |
| `database_transactions.query_view` | Ordinary admitted read outside a transaction; registered exact query lease inside | Not duck-typed access to any object exposing a connection |

The launch adapter is narrower than storage support. `sqlite_launch._admit`
selects full-source application routes for v13/v15/v16, explicit legacy routes
for v6/v7, and tightly restricted plain catalog routes for v1/v2/v3/v4/v10/v11/v12.
It refuses other profiles rather than inferring activation from available tables.
In particular, `launch_snapshot` does not advertise every storage format as UI-ready.

Keep historical fixtures and their identity/hash boundaries. Consolidating the
user-facing demo does not authorize rewriting captured native evidence or
silently converting old DB formats. There is no new migration engine in this audit.

Implementation anchors: `database_context.py`, `sqlite_catalog.py`,
`sqlite_launch.py`, `source_constant_store.py`, `database_transactions.py`,
`inventory_enum_runtime.py`, and the explicit `sqlite_*_profile.py` modules.

## Receipt reclamation design boundary (M1)

Current root receipts are host-lifetime envelopes, explicitly not durable restart
tokens. `RootOperation.run/resolve` marks an outcome accepted only after participant
installation. COMMIT success alone is insufficient. An uncertain state, cleanup
failure, unresolved receipt, or a merely committed/unaccepted result must retain
all recovery evidence. The original checkpoint had no receipt acknowledgement/GC API. The opt-in v2
duplicate-payload compaction contract is described in
[root-receipt-acknowledgement.md](root-receipt-acknowledgement.md); it does not delete child receipts.

The storage root binds ordered child operation IDs, request hashes and complete
child outcome bytes. `sqlite_transactions.resolve` checks these children before
returning outcomes. `begin_write` uses persisted receipts to reject operation-ID
reuse. Thus neither deleting children alone nor deleting an entire successful
journal is safe: the first breaks recovery, the second permits replay.

Before enabling deletion, an explicit retention protocol must provide:

1. A root-owned acknowledgement after accepted outcome installation, bound to the
   exact database, generation, operation and frozen ordered requests/outcomes.
2. A compact durable tombstone that continues to deny operation-ID reuse and
   distinguishes acknowledged history from genuine absence. Recovery must never
   translate an acknowledged result into `None` and authorize replay.
3. Atomic tombstone installation plus child cleanup, with compare-and-check of
   exact receipts in the same writer transaction. No callback or posting replay.
4. Idempotent acknowledgement after a lost response; corruption, changed bindings,
   foreign roots and unresolved states fail closed without deleting evidence.
5. Compatibility with `sqlite_configuration_history` receipt epochs. That format
   explicitly requires old receipts to remain byte-for-byte present; those receipts
   must be retained until a separately admitted compatible protocol exists.
6. Crash injection before and after each atomic boundary and reopen tests covering
   acknowledged, committed-unaccepted, uncertain, conflict and missing states.

No runtime deletion is enabled by this document. Introducing an unversioned marker
into existing canonical receipt JSON would silently change existing resolver and
schema contracts. Preserve the receipts instead of disguising that as a safe GC.

### Disposable-database counterexamples

`tests/test_receipt_retention_frontier.py` exercises four current-format cases
using a newly created temporary posting database for each test. It never deletes
receipts from an existing user database:

* Even `accepted=True` retains independent root and document-child UUID guards.
* Deleting only the document child makes root resolution fail `integrity`, while
  opening a new unit of work under that child UUID becomes possible. Retaining
  only a root tombstone therefore does not preserve the existing child-ID guard.
* Deleting only the root changes resolution of a known committed operation to
  `None` and admits that root UUID again. Child receipts do not repair this.
* Replacing the existing payload with a compact unversioned acknowledgement
  object fails the old resolver's contract, though its root-ID guard remains.

These are counterexamples to proposed deletion shortcuts, not a GC feature or
an endorsement of the deliberately corrupted states. A future deletion-based retention
profile would need versioned acknowledged-resolution assertions. The v2 root
compaction instead keeps every child outcome and rehydrates exact v1 bindings. It must retain enough identity tombstones to deny reuse
of both roots and children. Exact historical outcome recovery cannot be promised
once those outcomes are discarded; the new acknowledged result must be explicit,
not silently mapped to absence. Fixed-size tombstones can bound retained payload
per operation but do not bound the number of operation identities. A retention
horizon would itself require a different, explicit operation-ID lifetime contract.
