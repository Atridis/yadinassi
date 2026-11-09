# Callback descriptions and direct dispatch

This is one in-process language family: `ОписаниеОповещения` /
`CallbackDescription` and `ВыполнитьОбработкуОповещения` / `RunCallback`.
It uses the existing BSL routine dispatcher and cooperative scheduler. It does
not introduce another interpreter, source evaluator, event loop or RPC layer.

## Ordinary contract

```bsl
// Handlers.bsl: initialized once when explicitly imported.
Var Calls;
Function Complete(Result, Additional) Export
    Calls = Calls + 1;
    Return Result + Additional + Calls;
EndFunction
Calls = 0;
```

```bsl
// Main.bsl
// #Import Handlers.bsl
Callback = New CallbackDescription("Complete", Handlers, 10);
First = RunCallback(Callback, 5);   // 16
Second = RunCallback(Callback, 5);  // 17, same module state
```

Names are case-insensitive; Russian names are equivalent. The handler must be
exported in an initialized client module. A function's value is returned; a
procedure returns `Undefined`, including when `RunCallback` appears in an
expression. `Result` defaults to `Undefined`. Dispatch supplies two values in
order: `Result`, then `AdditionalParameters`. Ordinary routine arity/default
rules apply; a handler with an optional third formal keeps that default.

Descriptions retain the module receiver and additional value. They may be
stored in variables, arrays or structures, returned by BSL functions, passed
through BSL parameters and used in nested or repeated chains. Module variables
remain owned by their original module, including when a different imported
module dispatches the description. Each call has an ordinary local frame.
Rebinding a handler's scalar formal does not rebind the caller's variable or
replace the captured additional value. Mutations of shared arrays/structures
remain visible, as with ordinary same-process BSL object arguments.

`ThisObject` / `ЭтотОбъект`, an already imported module name, or a stored module
receiver can select the module. A string module name is a bounded Yadinassi
convenience for an **already imported** name (including `Package.Module`). It
never triggers an import, resolves a filesystem path, or loads arbitrary code.
Dynamic `New("CallbackDescription", Arguments)` and `New(Type(...), Arguments)`
use the same constructor.

The constructor admits zero to five arguments and omitted slots. In this local
profile, omitted procedure/module and error-handler fields read as `Undefined`.
An incomplete description can be stored but cannot be run. Readonly RU/EN
properties are `ProcedureName`, `Module`, `AdditionalParameters`,
`ErrorHandlerProcedureName` and `ErrorHandlerModule`. No Python attribute or
callable is exposed. Self descriptions can be created during module
initialization, but public dispatch waits until initialization succeeds, like
existing `ThisObject` exports.

## Errors and Async/Await

Handler lookup, required Export, arity and body errors use ordinary BSL errors.
`Try/Except`, `ErrorInfo()` and source locations work through the existing error
stack. Effects before a failure are retained; callbacks do not create a
transaction or an automatic retry. A failed call restores routine frames so a
later callback can run normally.

An async function handler returns its existing scheduler-owned `Promise`;
`Await RunCallback(...)` receives its result or rejection. An async procedure
returns `Undefined` and reports failures through the existing async-procedure
host boundary. Awaited callback arguments, nested callbacks and sibling tasks
use the same task-local state as direct routine calls. Direct synchronous
`RunCallback` does not pump other tasks or implicitly await the handler.
These composition rules are local runtime tests, not a claim of a separate
measured native Async/callback profile.

## Explicit limits

- Only the current interpreter's shared import/scheduler family is admitted.
  Receivers/descriptions from another interpreter are rejected.
- Server and NoContext dispatch cannot regain client module capabilities.
  Server handlers, dual-context module exports and client/server transport of
  descriptions remain unsupported.
- Forms, commands, modal dialogs and asynchronous platform operations are not
  connected to this family. A form-like host object is not treated as a module.
- Error-handler configuration (constructor arguments 4 and 5 other than
  `Undefined`) is rejected explicitly, including an explicitly supplied empty
  handler name. There is no emulation of error dialogs, `StandardProcessing`,
  legacy compatibility modes, or a catch-all handler around completion code.
- Description instances and their type tokens cannot be serialized through the
  internal codec; no callback/module capability crosses a network or storage
  codec. No GUID or native serialized representation is invented.
- Legacy English aliases `NotifyDescription` and `ExecuteNotifyProcessing`
  are not newly registered. The current names above are verified in official
  syntax help. Exact corner-case coercions, default property presentations and
  validation timing have not been measured on real 1C.

## Evidence and checks

Official EDT 2026.2 syntax-help archive:
[platform documentation JAR](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar),
SHA-256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
The Russian and English `SyntaxHelperContext` entries under
`objects/catalog1649/catalog1890/CallbackDescription`, constructor `ctor190`,
and `objects/Global_context/methods/catalog27/RunCallback4451.html` establish
modern names, optional constructor slots, readonly properties, two dispatch
arguments and return behavior. These are documentation, not captured execution.

[Developer Guide 8.3.27, §4.7.9.2](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/)
also describes function/procedure results and the operation-specific error
handler. [Official 8.3.22 release notes](https://dl05.1c.ru/content/Platform/8_3_22_2239/1cv8upd_8_3_22_2239.htm)
separate asynchronous-operation failures from completion-handler failures.
`RunCallback` must not become a generic callback-error interceptor.

`tests/test_callbacks.py` covers the functional family and its composition with
imports, ordinary errors and Async/Await. This change adds no native fixture,
synthetic native output, or integration-run result. Native edge calibration can
be added separately without blocking the useful ordinary language workflow.
