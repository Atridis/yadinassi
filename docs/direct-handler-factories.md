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
