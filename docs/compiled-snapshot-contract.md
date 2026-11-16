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

In this FORCE-translation branch, executable compiled units require the snapshot
contract. The constructor still accepts `compiled_ast_contract='mutable'`, but
execution rejects it with `force translator requires owned snapshot`; it does not
switch to the interpreter. Historical mutable-AST detection tests explicitly
disable FORCE and do not establish support for that production combination.
A family captures one contract and cannot silently switch it in a child. Scoped
policy and scheduler callbacks propagate the captured contract.

The historical owned FULL/OFF experiment matrix remains separately instrumented
in isolated tests; it is not the production selection interface.

## Validation status

Snapshot and historical mutable compatibility have separate explicit tests.
Production FORCE additionally tests explicit rejection of the mutable combination.
Passing tests that assert a mutable AST rejection does not establish snapshot behavior. Likewise,
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

## Explicit entry admission

An admitted syntax node is not necessarily a generated executable entry: nested
statements and metadata may belong to a prepared unit without a singleton entry.
The public `visit(node)` boundary explicitly prepares a missing entry before its
first effect. Internal generated node/block lookup does not compile on demand and
still rejects missing routes. Quiescent release may discard an entry; a later
public visit admits it again under the same limits.

Whole-unit FORCE admission checks expression, assignment-target and routine
parameter roles for ASTs supplied by embedders. Invalid roles reject before any
earlier statement can affect the host. Metadata-only nodes do not become executable
statements. Server initializers remain module metadata with separately prepared
bodies. These checks execute during admission, not in the generated hot path.
Standalone expression research helpers retain their separate delayed-error
contract; they are not evidence of whole-unit admission completeness.

This does not extend native language coverage or lift context restrictions.
Cross-context non-Val actuals still require named variable storage; property/index
copy-back and jumps into inactive blocks retain their explicit unsupported bounds.
The original 20-second collections performance gate is a separate remaining goal.
