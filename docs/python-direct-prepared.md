# Explicit reusable direct modules

```python
from decimal import Decimal
from yadinassi import Interpreter

vm = Interpreter()
vm.variables['x'] = Decimal(0)
module = vm.prepare('x=x+1;x;', source='counter.bsl')
assert vm.execute_prepared(module) == 1
assert vm.execute_prepared(module) == 2
```

`vm.prepare_program(parsed_ast)` is the equivalent entry for an already parsed
AST. Preparation compiles once. Ordinary `execute` and `execute_program` still
compile on each call: there is no hidden AST-identity cache.

## Snapshot and compatibility contract

The prepared object owns a structural copy of the input AST. Subsequent edits
to the caller's AST do not alter this program: prepare again to use those edits.
This is always snapshot semantics, even if `compiled_ast_contract` is `mutable`.
Only immutable parser literal payloads are supported (including Date and Null);
arbitrary host/mutable literal payloads are rejected without invoking host
`deepcopy` hooks. The frozen object has private implementation fields whose
mutation is unsupported; it is not an adversarial-object security boundary.

The program is portable code, not cached authorization or an owner-bound VM
capability. `other_vm.execute_prepared(module)` is supported when its direct
backend, native target, compilation profile, AST-contract selection and module
name layout match. The layout includes the program's own top-level Var names.
Adding/removing other declared module names requires preparation again, because
it can change routine-local versus module-global binding. Ordinary values can
change freely; reads/writes use the current exact `vm.variables` dictionary.

Every run repeats current VM/context, policy-hook, constructor and host-registry
admission. The current host registry is selected anew; in-place registration
changes remain visible at subsequent host boundaries. Replacing the entire
registry dictionary *during* a callback has the same existing direct-route
limitation: that execution's boundary context retains the original dictionary.
There is no new arbitrary mid-execution registry-rebinding guarantee.

A currently closed interpreter is rejected before source effects. The existing
ordinary `execute` API can explicitly reopen a standalone root; after reopening,
the old prepared code is usable again. A prepared object is not a family
revocation token. Restricted contexts and host-boundary context changes remain
rejected. Each run uses a fresh execution shell; the prepared object stores no
VM, results, namespace, outputs or last-run state. Existing direct-route parity
limitations still apply; this API does not enable configuration/server execution
or persistence of source routines across independent modules.

## Measurements

`experiments/direct_prepared/benchmark.py` records explicit preparation, first
execution, and seven alternating warm pairs. The baseline is
`execute(source)`, including parsing and compilation, not
`execute_program(preparsed_ast)`. All invoice/graph result fields
and 1,000 callback values/order are checked on every run. Synthetic fixtures are
not real-1C evidence. Times below are milliseconds, without pass/fail thresholds.

| Case | Ordinary execute warm median | Prepared warm median |
| --- | ---: | ---: |
| Invoice, 1,000 rows | 42.120 | 9.010 |
| Graph, 1,000 nodes | 54.165 | 11.322 |
| Arithmetic, 10,000 iterations | 3.393 | 2.343 |
| Source byref, 10,000 calls | 7.417 | 5.342 |
| Source by-value, 10,000 calls | 4.687 | 3.086 |

The one-off preparation samples were 41.452 ms for invoice and 101.848 ms for
graph (single noisy samples, not medians). Preparation plus the first execution
can cost more than ordinary execute. The improvement is repeated reuse, not a
claim that cold compilation became faster. Raw first-run, prepare and warm rows
are retained beside the script. Thirty-two focused prepared/default tests pass.
