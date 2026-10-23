# Bounded server NoContext implementation and evidence

`&AtServerNoContext / &НаСервереБезКонтекста` now denotes server execution
without module-context capability. This is not an alias of `&AtServer`.
The standalone entry point and unannotated routines remain client code.
The implementation follows two independently audited captures on native
8.3.27.1508, Linux/amd64, managed application, file infobase. The final changed
source still requires a fresh strict134 native run and four-OS CI before merge.
No forms, form attributes, database, query engine or network RPC are implemented.

## Compiler and visibility

The compiler selects a separate NoContext body. Its logical `AtClient` and
`AtServer` predicates are both false, while runtime execution remains on the
server. Standalone target defaults remain `Client=False, Server=True` for this
profile. They are not equated with the measured platform file-mode flags.
There is no invented `#If AtServerNoContext` keyword.

NoContext annotations apply only to top-level procedures/functions, not `Var`.
NoContext routines can call other NoContext routines, but cannot read module
variables or access the implicit ThisObject/ЭтотОбъект module receiver, or call
context-bearing server/client routines. Explicit parameter/local names can still
shadow that receiver name. The call restriction
is checked before actual-argument effects. Parameters and locals remain visible;
a local assignment cannot write hidden module storage. `Execute` and `Eval`
retain the same capability restriction. Unsupported dual directives still fail.
Same-name routines from different context families in one compilation are
rejected before root effects; a later persistent execution can replace a routine.

These visibility restrictions follow the primary
[8.3.27 Developer Guide, §4.8.1.3](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293),
which distinguishes out-of-context server methods from form-context methods,
excludes module variables, and lists allowed callees. The guide's
§4.8.1.2 separately enumerates preprocessor symbols. Command-module
`AtClientAtServer` and managed-form `AtClientAtServerNoContext` remain future,
distinct features; no common-module API support is implied here.

## Calls, parameters and errors

A client-to-NoContext call creates a detached logical server activation and uses
the existing bounded scalar/acyclic mutable Array/Structure packet contract:
named actuals are read after argument effects, expression results are retained,
packet occurrences are copied independently, and all outputs are validated
before normal-only positional copyout. An escaping exception suppresses
client-boundary copyout. Existing unsupported sink/type/cycle limits remain.

Calls from a context-bearing server routine into NoContext, and nested
NoContext calls, are same-side calls. They preserve ordinary local references,
including writes made before an escaping exception. They do not create another
client/server packet boundary. Returning or throwing restores caller capability
and diagnostics; imported client entry points cannot leak client error handlers.

## Initializer boundary: not a measured native guarantee

A direct NoContext activation has no module-variable storage and does not replay
the standalone explicit-server initializer. A NoContext call nested inside an
existing server activation hides that activation's storage without rerunning or
resetting it. This is the bounded autonomous no-module-context policy, covered
by local regression tests, not an independently established native initializer
lifetime result. The primary visibility rule alone does not prove every platform
initialization side effect. Full native initializer behavior remains an explicit
compatibility gap; arbitrary root statements and imports are never replayed.

The earlier unconditional-raising initializer preparation was not a valid probe:
it could fail during form construction before client entry. It was never
published or used as evidence. A future initializer experiment must observe a
bounded effect around actual calls, not infer semantics from startup failure.

## Audited captures

The source contains six literal client calls: four direct NoContext calls and
two calls to a context-bearing server wrapper. A second NoContext helper mutates
its scalar reference. Explicit locals avoid accidental managed-form properties.
All caller sink observations occur after return or EndTry; the Val recorder
cannot modify the observed sink.

Initial [run39992325017](https://github.com/Atridis/yadinassi/actions/runs/39992325017)
used head09dbc33a, treec597d5cc and sourceacebb0bf. Artifact12518806153 ZIP SHA256:
`7505db8d495779ddf3ff012a7ab40927153cd953f0d088df4dc4861c0dd3238d`.
Its vector was `[12,22,false,12,2,true,16,true,6,14,14,true,7,18]`.
The third value was the independently compiled `AtServer` predicate.

Profile [run39994534264](https://github.com/Atridis/yadinassi/actions/runs/39994534264)
used head548be3cb, treeb2dd8925 and sourcef87f6a48. Artifact12518298908 ZIP SHA256:
`156aa2f8190df6757e34a77a5e6b2db8bce501db4ecea7e6b23f88e94bd38fa2`.
Its vector was `[12,22,19,12,2,true,16,true,6,14,14,true,7,18]`.
Mask19 means Client1 + Server2 + ThickClientManagedApplication16;
AtClient4, AtServer8 and ThickClientOrdinaryApplication32 were false.
Each bit had its own conditional, not an Else chain. These are target-specific
observations, not a universal flag model or evidence of client execution.

The other thirteen slots were unchanged: nested12, private22, caller12,
Val-caller2, caughtTrue, caught-caller16, escapedTrue, escaped-caller6,
server-wrapper-normal14, server-wrapper-escape14, wrapper-caughtTrue,
recovery-input7 and recovery-caller18.

Both captures deliberately failed strict119 equality because of extra values.
Their completed marker phase is not successful probe validation. Later client
parity suites and watchdog were not started. Neither capture is full parity.
Source/module/roundtrip, nonce, all24 staged pins, interpreter provenance and six
baseline server cases were independently audited, together with the restored119
host preflight. The PR merge commits bind the same reviewed source trees.

## Final strict witness and release gate

The final source replaces the six target bits with only logical AtClient/AtServer
bits, both expected false from the audited profile. Other thirteen observations
are unchanged. The v3 sentinel prevents confusion with earlier captures.
The strict contract is134 values: original119 + sentinel +14 observations.
The zero logical mask is a projection of measured bits into new source, not a
claim that this new source has already passed native validation.

Temporary public capture payloads and restored-source host execution are removed.
Host preflight executes the entire exact staged source, independently computing
all134 typed values; native must satisfy the same strict contract. Finite failure
diagnostics never accept mismatches. The hash-bound inverse remains only for
legacy adapter construction and must restore the exact old a3e4fd9b source;
all four historical generated modules remain byte-identical. No generalized
strip, security-reader relaxation, cap increase or reduced coverage is allowed.
Production serializer checks cover417 finite failure variants: wire7,984/8,192,
late public report32,159/32,768, early28,197 and provenance15,011/32,768 bytes.
These conservative shapes are local bound proofs, not accepted native reports.
Fresh current-head native134, four client parity runs, watchdog, provenance audit
and four-OS CI remain required before ready/merge. Async fixture semantics and
standalone target defaults are unchanged.

## Async runtime integration

The implementation is integrated on actual main
`ad12e6db946805e9dd4663a4af45c85dbbc49646` (tree
`2f9724eb378aa4e687b395e6037581cfd6f4b9d5`). Module capability belongs to
`ExecutionContext`, not a shared interpreter instance: task creation copies the
stack, task resumption restores its own view, and routine cleanup pops it even
when initialization or execution fails. Detached diagnostic owners are removed
on the same outer cleanup path. Client Async routines retain module capability;
NoContext/server Async declarations and Await in NoContext bodies remain invalid.

Local composition regressions cover interleaved suspended client callers,
NoContext copyout/escaping errors after Await, initializer recovery, implicit
receiver hiding and detached-owner lifetime. These are not additional native
observations of asynchronous server methods. The existing eight source-bound
Async cases and comparator remain unchanged. Current-tree acceptance requires
both strict134 native/host parity and a fresh source-bound Async8 run, plus
four-OS CI; historical acceptance of either parent cannot substitute for it.
