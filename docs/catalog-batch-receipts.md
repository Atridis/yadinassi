# Recovering an atomic catalog write batch

This is the host catalog backend's local persistence contract, not a new BSL
transaction API or a claim of native 1C transaction parity. Existing transactions
can create and update several catalog objects atomically. A lost COMMIT response
must be resolved against the **whole ordered transaction**, not by checking that
one object exists or resolving its draft in isolation.

## Backend-neutral intent and capability

`CatalogWriteRequest(draft, expected_revision=None)` retains one successful
transaction write. `None` identifies a create; an update retains the exact
expected `Revision` submitted to `update`. The draft includes the original
`auto_number` request and section replacement/preservation choice. Keep these
requests in the order in which `create` and `update` succeeded, including repeated
updates of the same object. A record operation that failed and rolled back to its
savepoint is not included in the committed receipt.

The logical port advertises `Capabilities.catalog_batch_receipts`. Its default
is false so a future backend cannot silently promise recovery it does not
implement. Active SQLite v1/v2/v3/v4/v6 databases support the capability, including
read-only openings. Inert source archives do not. There are no SQL statements,
SQLite handles, or physical table names in the request/result contract.

- `resolve_writes(operation_id, requests)` returns the original ordered tuple of
  `Revision` values or `None` if no receipt is present.
- `resolve_write_outcomes(operation_id, requests)` returns the original ordered
  tuple of `CatalogWriteOutcome(revision, code)` values. It additionally requires
  `catalog_write_outcomes`, currently SQLite v4/v6. Generated codes come from the
  receipt, never from current object contents or a second allocation.
- `requests` is a tuple containing at most 10,000 `CatalogWriteRequest` values.
  An empty committed transaction resolves to `()`, distinct from `None`.

The APIs are read-only. They neither execute the requests nor create a receipt,
advance a counter, repair data, migrate the database, or invoke object modules.
Existing single-object methods remain available and reject a partial request for
a multi-write receipt. `committed_operation` is still an inspection API; the
presence of a receipt alone does not validate the caller's retained intents.

## Recovery procedure

Choose and retain one operation UUID and the intended requests before attempting
the transaction. Do not replace them after an uncertain result. For example,
using an already admitted backend and two host-prepared drafts:

```python
from contextlib import closing
from uuid import uuid4
from yadinassi.catalog_backend import BackendError, CatalogWriteRequest

operation_id = uuid4()
requests = (CatalogWriteRequest(first_draft), CatalogWriteRequest(second_draft))

try:
    with closing(backend.begin_write(operation_id)) as transaction:
        for request in requests:
            transaction.create(request.draft)
        revisions = transaction.commit()
except BackendError as error:
    if error.code != 'uncertain_commit':
        raise
    # Keep operation_id and requests. After releasing a failed connection,
    # resolution may use a newly opened backend for the same database.
    revisions = backend.resolve_writes(operation_id, requests)
    if revisions is None:
        # No receipt was present in the read snapshot. A caller may retry this
        # exact original transaction using the SAME operation_id. This API
        # deliberately does not perform that retry.
        pass
```

Keep a durable application-specific recovery record when recovery after process
termination is needed; these in-memory dataclasses do not supply a persistence
format. Requests must describe the writes that actually succeeded if the caller
catches individual write failures and subsequently commits the remaining writes.
Do not infer success from current cards: subsequent transactions may already have
changed their codes, revisions, scalar values or sections.

`None` is a receipt-absence result, not approval or validation of a proposed new
write. Retry still performs ordinary write validation. Reusing the same operation
UUID prevents a competing or late confirmed operation from being duplicated:
`begin_write` refuses an operation whose receipt already exists. An exception,
including `busy`, `schema_changed`, `storage_error`, `conflict` or `integrity`, is
not proof that the original transaction failed. Retain the original recovery
state and address the error; do not replay under a fresh UUID.

## Integrity and compatibility

Resolution checks the complete ordered canonical intent digest and every
returned identity/revision. Missing, extra, reordered or changed requests refuse.
A changed update revision, scalar, deletion mark, automatic-numbering flag or
section intent cannot silently match. Assignment qualifiers are applied exactly
as for the original write, so distinct input spellings that normalize to the
same canonical intent remain equivalent. `None` sections (preserve) and `()`
(replace with empty) remain different intents.

The stored format and historical receipt hashes are unchanged. Canonical intent
hashing streams one request at a time, rather than retaining another full batch
of scalar and section payloads. Per-record, section and transaction bounds remain
in force. This does not expand write limits or provide cryptographic protection
against an attacker who can rewrite the entire owned database.

V6 recovery retains its existing narrowly scoped receipt-only source check:
archived source drift can block new writes while still allowing resolution of an
already committed operation. Database/configuration identity or generation drift
is not ignored. Recovery does not reactivate changed source or bypass new-write
admission.

Owned SQLite tests cover ordered and mixed batches, cross-catalog and section
references, repeated writes, explicit and automatic codes, failures before and
after COMMIT, cleanup failure, read-only recovery, later edits, corrupt receipts,
legacy v1 and historical hash compatibility. Native integration scenarios and
observations are unchanged because no native behavior surface is added.
