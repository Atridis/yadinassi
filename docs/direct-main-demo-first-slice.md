# Direct MVP: first real managed-form slice

This Draft iteration is **not a runnable full main-demo application**.

Verified using the real 47-file examples/demo export: XML import, creation and
reopening of a temporary SQLite main-demo database, then the actual DemoWelcome
server Created procedure executed as generated Python and updating Greeting.
The test forbids Interpreter.block/call_routine and verifies unchanged DB bytes.
Database schema creation is existing host code, not translated BSL database CRUD.

## Small mechanisms retained

* Declaration-only generated Python factories produce callable procedures.
  Signature AST tables remain metadata for existing form bindings only.
* Compile-time external names lower directly to the existing typed form getter
  and setter. Values are never copied into a shadow namespace. Explicit locals
  and parameters retain ordinary Python storage and shadow form attributes.
* Each event receives a fresh boundary and side-local activation state. Existing
  event lock, revision, ownership and field validators remain product boundaries.
* Generated loop headers charge the event budget. This is **not** old AST-node
  accounting. Infinite loops are stopped; exact step-count parity is not claimed.
* Transaction helpers are explicitly disabled during events, restoring the prior
  flag afterward. Review reproduced server BeginTransaction incorrectly reaching
  a client-bound service before this correction; a mock regression prevents it.
* Closed interpreter generations and restricted transaction/safe-mode contexts
  reject. Configuration-runtime and specialized source-form contexts remain
  unsupported rather than inheriting incomplete authority checks.

## Known unavailable or incompatible scenarios

Full application startup currently stops at common-module configuration admission.
BSL DB CRUD stops at database-context admission. No implicit legacy fallback.
Host member access, dynamic form builders, replicated endpoint function calls and
cross-side service routing have not been connected by this slice. A successful
Created handler does not prove these scenarios work. Bare form-attribute byref
remains unsupported, whereas event argument slots support byref and Val.
FormSideProgram has no retained source text, so direct error source lines can be
missing. ErrorInfo/ErrorDescription still reference the old interpreter error
stack and do not provide full direct Try diagnostics. Python 3.10 source-position
incompatibility remains. Trusted Python callbacks are not sandboxed.

The original main-demo runtime and application-process end-to-end tests were
rerun: both now pass import/schema setup but remain errors at the two admissions
above. No native 1C fixture was modified and no full parity claim is made.

Focused reproduction:

```
PYTHONPATH=.:tests python -m unittest test_python_direct_forms \
  test_python_direct_handlers test_python_direct_external_namespace
```

The legacy backend remains explicit; its FormSession execution branch is unchanged.
