# Explicit host unit-of-work and storage migration

This is a host Python API for an owned SQLite database. It is not a BSL
`BeginTransaction` implementation. Existing catalog/document/register `Write()`
methods still commit their own standalone operations. A staging ticket must not
be presented as a successful durable object write.

## Enabling the storage profile

Opening or creating a database does not upgrade it. Stop **all** processes that
can open the database, retain and verify an operator backup, then create and save
an explicit plan:

```sh
python -m yadinassi.storage_migration_cli plan owned.sqlite --maintenance --plan-file upgrade.json
python -m yadinassi.storage_migration_cli apply owned.sqlite --maintenance --plan-file upgrade.json
```

The new format is 11. Its retained base layout is 2, 3, 4, 7, 8, 9 or 10;
metadata, records, sequences, existing receipts and configuration archives are
not rewritten. The additional profile, migration marker and common receipt
infrastructure are created in one exclusive SQLite transaction. A document
query-order index is installed for document-capable profiles; each catalog gets
a canonical UUID-order index with its versioned comparator registered on all
backend and migration connections. The plan lists
exact DDL and is bound to a fingerprint of the source, not just its version.
`format_version` identifies the physical format; `storage_version` retains the
base layout semantics for the existing ports.

Versions are feature profiles, not a universally traversable upgrade ladder.
Inert/demo profiles 5 and 6 are explicitly refused by this migration. The
existing `prepare_v1` / `migrate_v1` API remains the separate supported 1-to-2
transition. Schema changes, feature conversion and downgrades are not supported.

The `plan` command only reads the database and creates a **new** plan file. It
never overwrites an existing recovery plan. It does not make a backup. An
`uncertain_commit` must be resolved while maintenance remains in force:

```sh
python -m yadinassi.storage_migration_cli resolve owned.sqlite --maintenance --plan-file upgrade.json
```

A matching version alone is not proof. The resolver checks the exact marker,
profile and retained source. `uncertain` is not permission to rerun the migration
or proof of data loss. A changed database, inaccessible file or recovery-needed
journal requires operator investigation.

## Staging a mixed transaction

```python
from uuid import uuid4
from yadinassi.transaction_backend import TransactionRequest

operation = uuid4()  # Retain this and the exact immutable requests for recovery.
requests = (
    TransactionRequest('catalog_create', catalog_draft),
    TransactionRequest('document_create', document_draft),
    TransactionRequest('register_write', register_draft),
)
with backend.begin_unit_of_work(operation) as tx:
    tickets = tuple(tx.stage(request) for request in requests)
    # tx.read_catalog/read_document/read_register see the staged writes.
    outcomes = tx.commit()  # Only this returns durable typed outcomes.
```

Supported kinds are `catalog_create`, `catalog_update`, `document_create`,
`document_update`, `register_write`, `register_delete` and `register_set`.
Updates carry the exact expected revision in `TransactionRequest.expected`.
Register writes without an expected revision create a record. Register deletion
requires the expected revision. Register-set replacement uses its existing
snapshot guard in the draft.

The context owns one connection. Child port writes cannot commit it. Each stage
has an atomic savepoint covering its SQL, numbering, journal and child receipt.
If the host catches a rejected stage, earlier successful stages remain pending;
it can explicitly commit those or roll back the whole unit. Leaving the context
without commit rolls back. There are at most 256 operations and a shared 16 MiB
intent/outcome budget. Repeated writes to the same catalog/document identity,
and overlapping mutations of the same register, are explicitly refused in this
initial contract. Multiple different documents/catalogs are supported.

After an uncertain commit response, close the failed unit and recover with:

```python
outcomes = backend.resolve_unit_of_work(operation, requests)
```

The resolver verifies the ordered root binding and every typed child receipt.
Changed/reordered requests do not confirm the batch. `None` means no common
receipt was found in the admitted database snapshot; callers must not interpret
an inaccessible database or a raised error as that result. Never retry only one
child or overwrite the retained drafts with edited frontend buffers.

The host must propagate outcomes to frontend objects **after** complete commit
or resolution. This module does not change object `IsNew`, revisions, automatic
numbers or pending-write state provisionally, and does not claim ambient BSL
transaction compatibility.
