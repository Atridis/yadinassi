# Direct source nonposting document object modules

Document initializers, OnWrite(Cancel), and same-server module exports execute
as generated Python. The specialized source interpreter remains only the
canonical module owner and namespace holder; AST evaluator entry points are not
used as a fallback.

This is an execution-path migration, not new posting support. The existing
nonposting writer and its event blockers remain unchanged: BeforeWrite, posting,
undo-posting and other unsupported event contracts cannot be silently skipped.
Posted remains readonly through the canonical property writer.

## Preserved lifecycle

Initialization keeps its original transaction/admission frame and failure cleanup.
Loaded fields and section buffers replace initializer defaults afterward. The
canonical writer stores scalar data and sections atomically, invokes OnWrite,
and rolls back the transaction and object revision on cancellation or exceptions.
OnWrite buffer mutations do not cause an implicit second save. Caller-owned
transactions remain caller-owned.

The direct adapter binds exact object/interpreter/manager/store/definition
identities, rechecks field definitions and current section ownership, and retains
source scopes, safe-mode frames, signature scans and constructor validation.
Legitimate Read/GetObject replacement of section buffers is allowed; detached
sections and rows retain the original revocation checks.

Field expressions retain field lookup. Date()/Дата() calls retain canonical
builtin dispatch even though Date is also a document field. Bare and captured
standard methods use canonical descriptors, not unguarded Python callables.

## Verification

The existing document module lifecycle and guard suites run again with legacy
program and routine entry points poisoned. They cover scalar/section rollback,
OnWrite ordering, defaults, field references, exported state, loaded buffers,
unsupported events, recursion, transaction takeover and direct-store bypass.
Additional admission tests cover foreign/unsealed/stale owners and malformed
section ownership. No native 1C execution or posting parity is claimed.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_document_no_vm \
  test_python_direct_source_document_handlers_security \
  test_python_direct_source_document_guards
```

Final local evidence: 792 focused/compiler tests pass on Python 3.12; Python
3.10 `-O` passes the same suite with the existing Python 3.11+ SQLite limit API
skip. The 1,228-test source-only suite remains red at 141 errors and 26 failures,
23 fewer errors than the catalog checkpoint, with no newly failing identities.
The pre-existing unsealed-document guard now expects the precise direct-owner
rejection text; its poisoned SQL/VM and unchanged-storage assertions remain.
