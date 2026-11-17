# Direct source Query and storage slice

This increment builds on direct source startup. It does not select the legacy
AST evaluator or admit its specialized object/form interpreters.

## Supported crossings

* Source-owned Query construction and Execute/ExecuteBatch use the actual caller
  and the existing source query binder, package limits and immutable snapshots.
  Persistent input checks stay in the original source reader. Queries over only
  in-memory data do not acquire a scratch-database requirement.
* Exact detached query results, selections, value tables/rows/columns, arrays,
  type descriptions and temporary-table managers expose their existing finite
  public protocols. Detached scalar data is not an ownership capability.
* Constants expose Get/Set, selected sets, value managers, indexed lookup and
  iteration. Writes run the original descriptor dispatch and transaction
  pipeline, never the lower-level convenience writer that bypasses handlers.
* Catalog managers and no-module objects retain canonical CreateItem, lookup,
  read/write, selection and reference protocols, including saved methods and
  property by-reference slots. Actual source owner, reference identity,
  metadata snapshot, safe-mode and transaction checks remain in force.
* Neutral Catalog/Document manager reference operations retain their own
  actual-caller checks. Document object lifecycle is not admitted here.

The finite synchronous driver accepts only an exact generator and requires
completion without suspension. Unexpected suspension closes the generator,
allowing its transaction cleanup to run, and raises an uncatchable boundary
violation. It never interprets a yielded AST operation.

## Deliberate exclusions

Catalog object modules remain rejected before constructing their specialized
legacy interpreter. Constant value-manager modules are now handled by the
[bounded direct constants adapter](direct-source-constants.md). Legacy-created
objects with an attached interpreter still cannot enter the direct adapter.
Unsupported handlers are never skipped; existing legacy backends are unchanged.

Forms, document lifecycle, manager-module exports, cross-side calls and general
interpreter-aware descriptors are not enabled by this slice. Foreign queries,
foreign source namespaces and reference callbacks do not acquire permissions
from detached table or result protocols.

## Evidence

The same 1,228 source-only tests previously reported 570 errors and 97 failures
on the startup slice. The final Query/storage run reports 423 errors and 49
failures: 195 fewer failing outcomes (subtest outcomes are not distinct tests).
The suite remains red, chiefly on the excluded specialized lifecycles.
Focused tests include poisoned legacy program/routine dispatch, no-module
writes, caller-owned transactions, byref fields, early arity/procedure rejection,
foreign ownership and argument-time safe-mode changes. No real 1C run is claimed.

Reproduce the dedicated adapter regressions (with project dependencies installed):

```sh
PYTHONPATH=tests:scripts:. python -m unittest \
  test_python_direct_source_query test_python_direct_source_storage \
  test_python_direct_source_storage_guards test_python_direct_source_storage_security
PYTHONPATH=tests:scripts:. python -O -m unittest \
  test_python_direct_source_query test_python_direct_source_storage \
  test_python_direct_source_storage_guards test_python_direct_source_storage_security
```

The pre-existing captured-constant foreign-owner assertion now requires the
direct backend's uncatchable boundary error; legacy still requires its original
BSL error. This strengthens the direct denial rather than dropping the check.

Final integration on StrConcat parent `a9a2170b`: 232 focused tests pass under
Python 3.12 and the same 232 pass under Python 3.10 `-O`, including startup,
query/package/lookup, storage/security and StrConcat regressions.
