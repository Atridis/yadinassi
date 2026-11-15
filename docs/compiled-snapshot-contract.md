# Compiled program versions and live application data

`compiled-strict` uses an immutable owned syntax version by default. This is a
program-version contract, not a frozen application or a Python sandbox. The
ordinary interpreter remains the separate compatibility oracle/rollback backend;
selecting the compiled backend does not silently fall back to it.

## Versions

A successful explicit, quiescent `execute_program(program)` prepares a new version
of the supplied graph. This includes reusing an AST object that the caller edited.
Unrelated existing routine declarations retain their prior admitted versions.
Reentrant execution cannot replace the version of an active graph. Failed
admission rolls back the new ownership mappings. New source through Execute,
Eval, imports or REPL goes through bounded explicit admission.

Editing an original AST after admission does not change already admitted code.
At scheduler quiescence, transient plans are discarded; routine-owned syntax and
compiled plans remain available while their declarations are live. Explicit
`engine.release()` discards all plans and ownership mappings. It is an explicit
host cache invalidation boundary, not an application-data mutation.

## Live data

Variables, Decimal values, by-reference arguments, opaque literal payload objects,
form objects, attributes, items, values and assignments of existing event handlers
remain live. Updating those values or bindings does not recompile existing routine
code. Handler lookup still validates activation, execution side and signature;
changing a form binding cannot grant permission to call arbitrary procedures.

Security grants, context checks, cooperative execution budgets, source diagnostics,
and dynamic-unit admission remain runtime checks, not cached compilation rights.
Owned-node identity and engine provenance must still be valid. This representation
is not a sandbox against unrestricted Python using object/list protocol bypasses.

## Explicit compatibility contract

Python callers that need the earlier fail-closed mutable-AST detection contract
can create `Interpreter(execution_backend='compiled-strict',
compiled_ast_contract='mutable')`. This is not interpreter mutation parity: that
mode rejects detected changes. A family captures one contract and cannot silently
switch it in a child. Scoped policy and scheduler callbacks propagate the captured
contract. Production interpreters do not read experimental Engine class flags.

The historical owned FULL/OFF experiment matrix remains separately instrumented
in isolated tests; it is not the production selection interface.

## Validation status

Snapshot and mutable compatibility have separate explicit tests. Passing tests
that assert a mutable AST rejection does not establish snapshot behavior. Likewise,
expected snapshot mutation differences must not conceal changes to values, error
locations, authority, budgets or by-reference effects. Source-bound broad gates,
context regressions, independent review and artifact checks remain required before
publication/merge claims. Timings from the earlier developer-only snapshot probe
are not production performance evidence for this implementation.

Private owned views are engine-bound implementation objects, not portable public
code objects. Passing an older owned view from another VM back through
`execute_program` is not a supported version-import API and may be rejected by
provenance/admission checks. Use source or an original source AST for explicit
admission in another VM; do not treat this limitation as permission to bypass
ownership validation.
