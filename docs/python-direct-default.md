# Python-direct is the default (breaking transition)

`Interpreter()` and ordinary CLI execution now choose `python-direct`.
Source is parsed once, lowered to Python, and executed against the same
`vm.variables` dictionary. Arrays/Maps/Structures use the direct representations;
source-local functions call Python functions, not the VM dispatcher. There is no
silent fallback when lowering or admission fails.

Use `yadinassi --legacy file.bsl` or
`Interpreter(execution_backend="compiled-strict")` for the preceding backend.
The reference oracle remains `execution_backend="interpreter"`. UI launcher
backend selection also accepts `--legacy`; default UI/configuration execution
may now refuse startup or events until its boundaries are integrated. This is
an intentional compatibility break, not evidence that existing product tests
all pass.

The default route does not require or modify
`YADINASSI_UNSAFE_COLLECTION_ABLATION`. Its internal trusted-entry parameter
bypasses that experiment opt-in only for this explicit backend. Manually calling
the experimental prepare/run API still requires opt-in. This gate is not a
sandbox against trusted Python embedding code.

## Supported slice

- Standalone exact base `Interpreter`, synchronous client context.
- Arithmetic/control flow and the supported direct collection operations.
- Same-source routine definitions/calls, including supported by-reference args.
- Canonical registered `HostFunction` services, resolved from the live registry.
- Shared module dictionary, callbacks observing/modifying it, retained module
  references and declared globals across repeated executions.
- `execute_program(parsed_ast)` lowers the supplied AST without reparsing.

## Explicit gaps and restrictions

- Configuration/database applications, Interpreter subclasses (including forms,
  posting and source NoContext contexts), custom policy/storage/visitor hooks,
  application safe-mode/transaction contexts, asynchronous/server routines and
  imports are rejected before translated source effects. The direct route does
  not bypass their old checks and does not claim their integration is finished.
- A source routine is currently local to one execute call. Calling its old name
  in a later execution fails explicitly; redeclaring it in that source works.
  Module variables and declared module names do persist.
- Same-VM reentrant execution, legacy routine/import registries and single-node
  `visit()` are not direct-module entrypoints.
- System namespace values, dynamic Execute/Eval-style interpreter services,
  custom constructors, arbitrary host-object member exposure, legacy collection
  wrapper interoperability and full error/runtime equivalence are incomplete.
- String ordering is native Python ordering in this direct profile, not the
  preceding UCA ordering. Decimal/native arithmetic equivalence is incomplete.
- Conditional local Var shadowing a module name is explicitly unsupported.
- Private generated routine locals are not exposed through `vm.locals`.
- This is trusted-process execution, not an untrusted-code sandbox. No custom
  per-node budget/ownership lease is added. Host services keep their explicit
  service boundary; Python interruption remains available.

The default gate rejects unsupported contexts rather than quietly routing them
through the reference interpreter. Existing compatibility-test failures must be
reported, not interpreted as permission to remove configuration or host policy.

## Verified transition checks

Focused default/API/CLI tests cover explicit legacy selection, live namespace,
AST lowering without reparsing, source-local calls, and fail-before-source-effect
admission. Public `visit`, `block`, `call` and `call_routine` cannot silently enter
legacy evaluation on a python-direct VM. Installing a restricted application or
safe-mode context from a host callback is detected at the returning host boundary
before subsequent source statements. The embedding must keep other interpreter
policy/storage bindings stable during execution; arbitrary concurrent Python
mutation is not a sandboxed interface.

The existing Array-default compatibility suite is currently red: legacy `.items`
wrapper/serialization expectations and FixedArray construction do not match this
route. Explicit empty native-call slots are also incomplete: for example,
`a.Insert(0,)` can currently mutate instead of rejecting the omission. Do not
mistake the focused smoke tests for a full compatibility pass.
