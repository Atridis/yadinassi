# Direct source catalog object modules

Catalog object-module initializers, BeforeWrite/OnWrite events and same-server
exports are compiled to generated Python. The original source catalog owner is
retained as a namespace/lifecycle holder, not as an AST evaluator. Legacy
program and routine dispatch are not a fallback.

## Lifecycle boundaries

The existing creation and writer orchestration remains responsible for recursion
limits, actual caller access, initializer transactions, event order, cancellation,
record revision rollback and closing failed owners. Loaded record values still
replace initializer defaults after initialization. OnWrite sees the stored record;
subsequent buffer edits do not retroactively change that write.

Typed fields, readonly Ref/ThisObject, module exports, default/byref arguments,
saved methods and bare standard methods go through canonical source operations.
The generated adapter keeps source and safe-mode scopes, owner admission seals,
exact interpreter/manager checks, namespace and signature checks, and native
constructor validation. Foreign or expired bindings cannot acquire authority from
another source caller. Admission does not bypass the store's handler-required
write token.

Document object handlers remain explicitly unsupported in this increment.
Unsupported catalog events, async/dual/NoContext routines, imports and Execute
remain rejected rather than silently skipped. Native 1C parity is not claimed.

## Tests

The existing catalog module lifecycle and guard suites are repeated with legacy
program and routine entry points poisoned. They cover cancellation, rollback,
initializer defaults, exports, typed field byref, recursive writes, transaction
takeover, safe mode and direct-store bypass rejection. Dedicated admission tests
cover unsealed, foreign, stale and altered object bindings.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_catalog_no_vm \
  test_python_direct_source_catalog_security \
  test_python_direct_source_storage_guards
```

Bare standard methods use an explicit trusted source-only callable-external
allowlist. It does not make arbitrary external namespaces callable, and ordinary
compiler profiles remain unchanged. Captured method expressions keep their
canonical callable descriptor and its delayed ownership checks.

Final local evidence: 593 focused/compiler tests pass on Python 3.12; the same
suite on Python 3.10 `-O` passes with one pre-existing Python 3.11+ SQLite limit
API skip. The final 1,228-test source-only suite remains red at 164 errors and
26 failures, down from 192 errors and 26 failures at the constants checkpoint.
No new failing test identities appeared; this comparison also includes the
intervening table-index increment. Exact store types and canonical field identity
are checked before lookup/equality callbacks; adversarial replacement tests
verify that neither fake callback runs.
