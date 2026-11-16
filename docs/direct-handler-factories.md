# Direct handler factories

`prepare_handlers` owns a snapshot of an already-admitted declaration-only AST.
It compiles separate client/server declaration factories, never executing a
module body. Side-local `Var` declarations use caller-state `setdefault`.
`bind` accepts procedures with the exact requested side and arity. Each `invoke`
creates a fresh boundary context and generated closure family, with explicit
by-reference cells and ordinary generated source calls. It does not invoke
`Interpreter.block`, `_visit`, or `call_routine`.

The embedding host must supply current side-local state, capabilities and an
invocation scope that enforces lifecycle/side admission before effects. Cross-side
calls require explicit service proxies. `external_names` is passed to the direct
namespace compiler for form fields; it is not permission to reflect arbitrary
host objects. This helper does not itself bind a FormSession or a database.

Source errors preserve generated source mappings; boundary violations remain
BaseException failures. Partial state changes are not rolled back. Opt into
`authority_checkpoints` and supply `loop_budget` when desired: this measures
loop headers, not the legacy VM's AST-node budget. Context cleanup runs on both
normal and exceptional exits. Prepared plans retain no event-specific state.

## Application-owned static forms

Exact `_FormInterpreter` instances bound to a configuration family now use the
existing configuration owner, lifetime, side, call and host-service checks.
Common-module names are explicit external names. Common-member calls use the
configuration adapter; this does not grant reflection on form or other host
objects. Handler registry identity is rechecked at event boundaries. Closed or
replaced owners fail before source effects; event transaction denial remains.

The real DemoWelcome Created and ShowDetails execute directly: greeting changes,
DemoService.Add crosses one additional transport packet, and DemoTools.OpenOperation
issues the expected OpenForm request. Opening OperationDraft itself is still
blocked during preparation by unsupported `ОписаниеОповещения` constructor in
its callback-bearing module. This slice does not emulate that callback with VM
execution or claim the entire process workflow passes.
