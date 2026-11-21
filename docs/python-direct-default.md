# Python-direct is the only execution backend

`Interpreter()` and the CLI use `python-direct`.
Source is parsed once, lowered to Python, and executed against the same
`vm.variables` dictionary. Arrays/Maps/Structures use the direct representations;
source-local functions call Python functions, not the VM dispatcher. There is no
silent fallback when lowering or admission fails.

The old interpreter, hybrid and compiled execution engines were removed.
Old backend selections are rejected, not redirected to another mode. UI and
configuration entrypoints report unsupported features explicitly. This is an
intentional compatibility break, not evidence that all product tests pass.
See [what was removed and what remains to migrate](direct-only-runtime-retirement.md).

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
- Exact string relational ordering now explicitly uses the existing bounded UCA10
  kernel; ordinal experimental profiles remain available. See
  [evidence and limits](direct-string-collation.md). Full native locale and
  Decimal/native arithmetic equivalence remain incomplete.
- Conditional local Var shadowing a module name is explicitly unsupported.
- Private generated routine locals are not exposed through `vm.locals`.
- This is trusted-process execution, not an untrusted-code sandbox. No custom
  per-node budget/ownership lease is added. Host services keep their explicit
  service boundary; Python interruption remains available.

The default gate rejects unsupported contexts rather than quietly routing them
through the reference interpreter. Existing compatibility-test failures must be
reported, not interpreted as permission to remove configuration or host policy.

## Verified transition checks

Focused default/API/CLI tests cover rejection of removed backends, live namespace,
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

### Missing routine-local names

Names without a lexical binding in a direct routine now raise a catchable BSL
undefined-name error with the original source spelling/location. They do not
resolve through generated Python globals or leak another side's module state.
This is a compile-time classification, not a blanket conversion of host
`NameError` exceptions, and adds no lookup to valid bound-name reads. Conditional
reads before a local assignment and other incomplete local/reference contracts
are not claimed fixed by this slice.

### Finite TextDocument operations

Standalone direct execution now admits the canonical `TextDocument` constructor
(including dynamic construction), its bounded in-memory text/line operations,
and ordinary bounded file `Read`/`Write`. The implementation reuses the finite
canonical resource adapter, not VM member dispatch or an arbitrary host-object
grant. Saved method values are checked again at invocation; exact class ABI,
state invariants, constructor aliases, and current boundary lifetime are checked.
Optional file encoding/separator slots use the existing defaults. Required holes,
UI/async operations, properties, indexing and iteration remain unavailable.

The existing 44 native TextDocument observations cover selected in-memory
behavior, not full parity: the historical aggregate comparison was red, and
mutator return-value expressions are not established by those observations.
File Read/Write and their encoding/newline options remain local extensions
without native observations; passing local tests is not new native evidence.
A server routine can use a document locally and return text; transport of the
TextDocument object itself between client/server contexts remains unsupported.

### Structured direct Raise

Direct Raise evaluates its description once, applies bounded BSL presentation,
then evaluates all supplied optional arguments left-to-right before validating
category, code, additional information and cause. Canonical immutable diagnostic
snapshots retain those fields and the original definition's source line; rethrow
retains the same snapshot. Category queries traverse exact canonical cause
snapshots without calling their Python attribute/equality/hash hooks. Malformed,
cyclic or over-1024-node host-supplied chains remain explicitly rejected. Reading
or calling a member of Undefined is a recoverable type error, not a database
receiver grant; arbitrary host receivers still fail closed.

The named 28-record exception/context projection matches the unchanged audited
Linux 8.3.27.1508 fixture exactly, with the complete input source SHA256 checked
before selecting its four marked helper/observation blocks. This is not a claim
that the complete historical 116-record functions program now passes: that
program still encounters an unsupported Goto. Native fixtures and integration
source are unchanged. Exact platform diagnostic formatting, other categories
and broader exception/runtime parity remain outside this slice.
