# Direct source constant value-manager modules

The direct backend now prepares constant value-manager declarations, initializers,
BeforeWrite/OnWrite events and same-server exported routines as generated Python.
The existing specialized interpreter is retained only as the canonical module
owner and namespace holder. Neither its AST program evaluator nor routine
interpreter dispatch is used.

## Preserved contracts

* The existing create/write pipeline still owns initializer transactions, batch
  admission, writer ordering, cancellation, typed Value encoding, rollback,
  recursion rejection and transient-manager cleanup.
* Module variables persist on a reused manager. Export visibility, ThisObject,
  default arguments and by-reference parameters retain their original contracts.
* Value references use canonical manager reads/writes, including type and actual
  caller checks. Source scopes and safe-mode routine frames remain active.
* A private admission seal binds the manager, owner, application, store and name.
  Legacy/unsealed, foreign, closed, expired and replaced owners are rejected.
  Generated checkpoints revalidate the owner, canonical hooks, namespaces,
  prepared signatures and constructor bindings. No registry scan is removed.
* Compilation completes before declarations are published or initializer
  effects start. Declaration-only construction does not execute an empty body.
* Qualified source calls now allocate the same lexical by-reference accessors
  as unqualified dynamic calls. The change is limited to source-routine scopes;
  other compiler profiles retain their previous dispatch.

## Explicit exclusions

NoContext, mixed-side/async/dual routines, imports, Execute in these modules,
FillCheckProcessing and event subscriptions remain unsupported. Catalog and
Document object handlers are not enabled. There is no fallback to the VM and
no claim of native 1C parity or a real-platform run.

## Verification

`test_python_direct_source_constants_no_vm` reuses the complete pre-existing
handler and module-lifecycle suites while poisoning legacy program and routine
entry points. It covers event order, cancellation, rollback, initialization,
exported fields, defaults, byref and safe-mode behavior. Additional security
checks exercise unsealed ownership, foreign lookup ordering, closed bindings
and changed declarations. Existing storage guards retain catalog rejection and
batch rollback checks; their formerly rejected constant initializer is now a
positive no-VM contract.

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_constants_no_vm \
  test_python_direct_source_constants_security \
  test_python_direct_source_storage_guards
```

Final local checks: 361 focused tests pass on Python 3.12; Python 3.10 `-O`
passes the same suite with one pre-existing skip for the Python 3.11+ SQLite
limit API. Another 28 compiler/array/byref regressions pass in both modes.
The 1,228-test source-wide suite remains red at 192 errors and 26 failures.
Compared with the previous forms checkpoint (227 errors, 46 failures), there
are 55 fewer failing outcomes and no newly failing test identities. That delta
also includes the intervening native constructor increment, not just constants.
