# Logical execution directives: first bounded implementation

Status: bounded implementation based on main `be82ce1`, independently reviewed
and validated for the Val slice by audited native runs (see evidence below).
Scalar non-Val strict whole-source acceptance passed audited actual-main native
run 39951594654. The current object-transfer extension is measurement-only;
see [object-transfer-measurement.md](object-transfer-measurement.md). Its host
preflight temporarily computes the exact hash-restored fifty-value scalar source,
not native-only object helpers. Unit results alone are not native evidence. Existing Async measurement work and historical parity fixtures remain
unchanged.

## Scope and execution model

The standalone root remains client code, as do unannotated routines and
`&AtClient / &НаКлиенте`. `&AtServer / &НаСервере` marks a server routine.
Client code can call it synchronously in an isolated logical server activation.
This is an interpreter context, not a 1C server, network transport, form, database
or query engine. There is no CLI server mode and native_target is independent.

Cross-side transfer accepts only `String`, `Number`, `Boolean` and `Undefined`.
Val parameters retain caller-side left-to-right value evaluation, including
existing defaults. Non-Val parameters now accept explicit named caller storage:
each formal gets a detached scalar input after all actual-expression effects.
On normal completion, every non-Val formal is copied out in parameter order,
including unchanged formals; repeated actuals therefore use the rightmost formal.
All result/outgoing values are validated before any caller write. Escaping server
exceptions perform no copyout; an exception caught on the server followed by a
normal return still permits copyout. Same-side references are not used to cross
the boundary. Property/index sinks, including forwarded references, and
unmeasured non-Val forms remain explicitly unsupported; object transfer is still rejected.

This is the measured **8.3.27.1508 Linux/amd64 managed file-infobase** subset, not
a universal claim for other targets. The official guide's alias/exception rules
disagree with this capture; see [scalar-copyback-measurement.md](scalar-copyback-measurement.md)
for exact evidence, interpretation and limits. File mode identifies the capture;
it is not an explanation for the documentation discrepancy.

Same-side server calls reuse ordinary call semantics, including recursion and
ordinary reference parameters. They do not create a new outer activation.
A server routine cannot call a client routine. Failed calls and thrown BSL
exceptions restore the caller's logical context. Client code can catch a server
exception; exact platform transport/category/stack metadata are not claimed.
Interpreter.execution_context is read-only and reports the active logical side.

## Compilation and procedure availability

Preprocessing is compilation-time, not a runtime switch around a shared AST.
The client compilation keeps client/unannotated declarations and the root body.
A separate server declaration compilation uses Server/AtServer true and
Client/AtClient false, and retains only explicitly server-annotated routines.
Server root statements and imports are neither executed nor installed.
Thus a server declaration entirely inside `#If Client` is unavailable on both
sides: its server compilation excludes the source and its client compilation
excludes the declaration. A declaration inside `#If Server` is server-callable.
The text still passes lexical validation; this is not a promise that arbitrary
malformed text inside unavailable routine declarations will be accepted.

A module containing the same routine name on both sides is explicitly rejected
before root effects in this first slice. This is an implementation boundary, not
a claim about native duplicate-name grammar. A later persistent execute may
replace a previous declaration, including its side, without leaving stale entries.

Runtime validates direction before arguments. Native compilers may diagnose a
statically invalid call earlier; the dedicated negative native fixtures distinguish
compile-time rejection from runtime failure. Do not call this exact diagnostic
parity before measurement.

## Deliberate limits and required subsequent work

- Annotated module variables are not implemented. Server activation has no
  client module storage, imports or ready public ThisObject receiver. Unannotated
  module variables remain client-only. Server locals must not alias client globals.
  This does not provide the full context-bearing module-state behavior of AtServer.
- Common named-variable scalar non-Val copyback is now the measured second
  slice. Object serialization and context-bearing module-state transfer remain
  required next parts, not optional polishing. Neither may be implemented as
  ordinary live Python/BSL references. Broader non-Val sink/default/expression
  forms need their own bounded contract before support is claimed.
- Server variable lifetime, nested server state, module exports and cross-module
  server dispatch require a separately measured state contract. Current imported
  server routines are callable from the client through the existing exported
  module syntax, but server routines cannot import client module state.
- AtServerNoContext follows after the context-bearing state contract exists;
  treating AtServer as an alias of NoContext would hide missing semantics.
- Dual-context routines need independently compiled client/server bodies and
  appropriate context visibility. AtClientAtServer is not an alias of the
  managed-form AtClientAtServerNoContext directive.
- The interpreter's existing builtins remain available on the logical server;
  this is not a full per-platform API availability catalog. Python host callbacks
  are the embedding application's responsibility, not native transfer evidence.

## Native plan and release gate

`integrational_tests/directive_probes/` holds independent source modules, not
captured outputs. The positive eleven-record witness observes real client→server
execution, preprocessing, nested server calls, scalar Val/results and caught
exceptions. Separate compile-negative modules observe direction and source
availability. Additional discriminators cover scalar copyback and server-variable
lifetime for the next increment.

A separately reviewed runner must create a managed-form module and invoke the
literal client entry after creation, preserving source hashes, side, version,
complete record bytes and bounded compiler outcomes. It must not use Execute to
pretend compilation directives were measured. No ready/merge claim until this
end-to-end witness is captured and audited against the exact candidate.

## Primary sources and project-specific choices

Official developer guide, sections 4.7.4.3 and 4.8.1–4.8.1.3:
https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293

The guide prohibits server→client calls, describes distinct compilation sides,
and specifies copies across client/server calls even in file mode. Its directive
reference distinguishes server-variable lifetime and no-context visibility.
These facts justify direction checking and forbidding shared mutable boundary
values. They do not by themselves authorize inventing standalone module state.

Official parameter guidance confirms that Val suppresses transfer back:
https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Clients/Optimizing_client_server_applied_solutions_for_SaaS_application_delivery_model/?language=en

Official directive-use guidance:
https://1c-dn.com/library/using_compilation_directives/

Native directives belong to platform module contexts. Mapping the standalone
root to client and running logical contexts in one process are explicit project
choices authorized by the user, not a claim that 1C executes standalone scripts
this way. The original fixed-client behavior is documented in features.md.

## Accepted scalar native witness (PR92 history)

The ordinary existing `--client-probe` includes eleven Val/context observations
and the 34 captured scalar-copyback observations plus their fixed version label.
Its original four values remain first and unchanged. No workflow
flag, image, process timeout, credential boundary, manual dispatch, database
query or async runner changes are required. Literal managed-form client code
calls literal server methods, never `Execute(text)`.

For the accepted scalar stage, the host ran the exact whole staged form source
through our interpreter in the existing bounded, credential-free subprocess,
calling only `ВычислитьПробу()`. Its computed typed values must equal the finite
contract. The native marker independently must equal that same typed contract,
with nonce, client OnOpen wiring, source/module/roundtrip hashes, clean process
exit and quiescence checks unchanged. This establishes bounded source-bound
witness parity by equality to the same contract, not by trusting labels alone.
The native marker remains private under existing policy; the public report
retains verified completion and source identity, not unvalidated raw output.

The scalar template had a new exact hash. Its narrowly checked legacy inverse
removed the appended Val/copyback suffixes and their two call blocks,
then verifies the original template hash
`4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328`.
All four existing parity adapters keep their original pins and produce identical
client-only modules. The separate PR90 async harness also touches this template;
any future merge must reconcile it explicitly and re-review the hash/inverse,
never relax either branch's source-binding rules.

Compile-negative and future-state discriminator modules remain separate planned
measurements, not fabricated captured evidence. The positive witness passed in
[native run 39932617220](https://github.com/Atridis/yadinassi/actions/runs/39932617220)
for head `46fafb9b9a171925f34a34e164b3a0c69b9bd285`, tree
`6306a2be0265bb78f3ed947f58f5c3306695246b`. Independent artifact audit verified
all 24 staged inputs, 50-file interpreter provenance, exact-source fifteen-value
host execution, native strict marker, module/roundtrip, nonce and process gates.
Source SHA256: `b98f7cb8e3489fabdd5df6cec8b929b7e059f9931f1fbfedb8d112be53c1f437`;
module/roundtrip: `ae7275f83f2be4976cfe42f3f7da71384f44c87130c3674c9a2d03e8a4f226b3`.
All four full client parity counts (841/185/421/402) were retained; existing
collections typed-map-order equivalence remains, not universal byte equality.
The subsequent Windows fixture/docs-only correction was validated on actual
main `1c3582a22f6a434bf10fd51c779ff5a15b2a2a42` by audited native run
[39939471860](https://github.com/Atridis/yadinassi/actions/runs/39939471860) and
four-OS run [39939471865](https://github.com/Atridis/yadinassi/actions/runs/39939471865).
This is historical Val-slice evidence, not acceptance of the new copyback implementation.

### Finite diagnostics after the first native run

The first native run reached the client entry and exited cleanly, with matching
source/module/roundtrip hashes, but rejected the completion marker. That result
alone does not distinguish a caught computation error from a typed value mismatch
and is not accepted directive evidence.

On rejected ordinary-client completion only, `marker_diagnostics` now reports a
finite phase (`invalid`, `error`, `completed`), mismatch class, zero-based value
ordinal (0–49, or 50 for excess values), and optional literal operation stage
(1–11). The BSL witness catches unexpected computation errors into a fixed
sentinel plus stage number, never error descriptions. Stage order is the eleven
labels in the positive probe; ordinal 4 is the first directive observation.
The original exact typed marker equality still rejects every sentinel, partial
result and mismatch. Metadata cannot grant success, export raw values or replace
source identity. The four old parity modules remain byte-identical.

### Measured target flags versus execution context

The measurement-only run [39931188144](https://github.com/Atridis/yadinassi/actions/runs/39931188144)
for head `83a85d440f5009242fc041cfddb02f00072e948a` produced client `111010`
and server `110110`, in order Client, Server, AtClient, AtServer,
ThickClientManagedApplication, ThickClientOrdinaryApplication. Both platform
Client and Server flags are true in this thick managed/file-mode target;
AtClient and AtServer discriminate the observed compilation contexts. This is
consistent with the [official preprocessor reference](https://1c-dn.com/library/preprocessor_instructions/).
The artifact was independently audited against all 24 staged input hashes and
PR tree `5e9161a0e9745b469cfbad99aff37d9b48c714e8` (the report identifies the PR
merge commit, not the branch head). Source SHA256:
`2e3224907a6919774a6c440739897f25f3b380256a3e8e6383ee6a91e1312de4`;
module and roundtrip SHA256:
`48fa1c4b5a830680e3d7379b2b0b6a6d795dd5b1a3ee44723a67ba6029e804a5`.
The complete witness was rejected at ordinal 5; these profiles are measurement
evidence, not accepted parity or a reason to change standalone defaults.

The positive witness now tests logical side with AtServer And Not AtClient and
AtClient And Not AtServer. Its matching subset explicitly excludes equivalence
of platform Client/Server target flags with standalone Client/Server defaults.
The first fifteen typed values remain unchanged. The earlier profile-only
helpers were removed before the audited Val run. The 34 audited copyback
observations and fixed version label extend scalar acceptance to 50 values.
PR92 passed exact complete-source execution, full native audit and four-OS CI
before merge; its temporary capture diagnostics/shared inverse were removed.
The current object measurement below introduces a separate bounded inverse and
finite diagnostics, without claiming whole-source object parity. The legacy
parity adapter inverse remains exact and byte-preserving.

## Current object measurement boundary

PR92 scalar copyback is merged and its actual-main native evidence audited.
The next object measurement appends eight calls/48 finite observations without
implementing object transfer. The existing strict fifty-value acceptance rejects
extras. Host execution currently uses an exact full-hash inverse to the accepted
scalar source, not whole-source object parity. The legacy parity inverse also
removes the appended object call block; all four modules remain byte-identical.
See [object-transfer-measurement.md](object-transfer-measurement.md) for the
bounded encoding, unchanged caps, source relationship and release gates.
