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

## Owned direct completions

CallbackDescription constructors now capture only the enrolled current client
self-form using the existing canonical descriptor and generation/enrollment
capability. Metadata validation is reused, not VM callback execution. Trusted
completion delivery retains revision/arity/export/lifetime admission and invokes
the generated handler directly; error cleanup and partial effects remain explicit.
ThisObject.Close is the sole newly exposed self-form method and delegates to the
existing owned-command close admission. Other host members stay denied.

Replicated client schemas arrive after initial declaration preparation. A change
in validated static/table names recompiles the owned declaration snapshot only;
value changes do not compile again. No renderer source is admitted. This resolves
OperationDraft's previously unbound client fields. Native Structure parameter/
result codecs are a separate integration dependency before the full owned-child
workflow can pass.

## Dialog enum namespace and accepted completion

QuestionDialogMode / РежимДиалогаВопрос and DialogReturnCode /
КодВозвратаДиалога are explicit read-only external names. Only the two existing
singleton namespaces receive public `get_member` reads. This does not enable
Python getattr, enum-class reflection, namespace assignment or arbitrary host
members. Existing typed dialog values, queue admission and one-shot tickets are
unchanged.

The actual main-demo child-process test now covers AcceptDraft → ConfirmDraft →
Yes, asserts AppliedCount=1 and the accepted outcome, then rejects a repeated Yes
without applying twice. Both forms close, the application closes, and the SQLite
file remains byte-identical. These tests and alias/private-access controls pass
under normal Python and `-O`; no legacy fallback was introduced.
