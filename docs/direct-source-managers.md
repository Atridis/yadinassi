# Direct source manager-module routing

Source manager namespaces now route explicitly declared exported routines to the
existing direct source module/routine boundary. This covers Catalog, Document,
Report, DataProcessor, register/chart, business-process, task and exchange-plan
manager namespaces in English and Russian, including dynamic manager names.

Manager modules use their own `('manager', family, name)` registry identity;
ordinary common-module keys remain a separate case, including a common module
literally named `Manager`. Every invocation revalidates the current module
registry, actual synchronous server caller and owner. Captured direct calls
cannot survive replacement or closure of their declaring module.

The direct routine bridge retains explicit defaults and by-reference argument
semantics, privacy/export checks, compilation profile, safe-mode routine frames
and source locations. Lazy manager admission still rejects module initializers
and variables before effects. No manager namespace grants implicit persistent
storage: built-in record operations retain their existing separate capability
checks. Client indexed lookup is denied before evaluating the index expression.

Not included: specialized forms, client-to-server crossings, handler-bearing
source objects and implicit local assignment shadowing read-only namespaces.
These remain visible failures rather than fallback routes to the VM.

## Evidence

On Execute parent `bc02f796`, the same 1,228 source tests report 278 errors and 47
failures, versus 332 errors and 49 failures before manager routing: 56 fewer
failing outcomes, including subtests. The broad suite remains red. Dedicated
regressions poison legacy program/routine execution and verify declared exports,
byref/default arguments, client/private/initializer denial, ownership revocation,
absence of storage grants and the common-module name collision.

397 focused tests pass under Python 3.12 and the same 397 pass under Python 3.10
`-O`, including the new manager regressions, preceding source slices and current
Execute/string tests. No existing assertion or CI gate was removed. Reproduce
the dedicated manager contract with:

```sh
PYTHONPATH=tests:scripts:. python -m unittest test_python_direct_source_managers
```
