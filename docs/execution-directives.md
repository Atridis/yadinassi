# Logical execution directives: first bounded implementation

Status: local implementation based on main `be82ce1`, awaiting independent
review and a genuine end-to-end native witness. Unit results are model tests,
not evidence of native compatibility. Existing Async measurement work, trusted
launchers, fixture bytes and CI source inventories are unchanged.

## Scope and execution model

The standalone root remains client code, as do unannotated routines and
`&AtClient / &НаКлиенте`. `&AtServer / &НаСервере` marks a server routine.
Client code can call it synchronously in an isolated logical server activation.
This is an interpreter context, not a 1C server, network transport, form, database
or query engine. There is no CLI server mode and native_target is independent.

The first slice accepts only `String`, `Number`, `Boolean` and `Undefined` at
client/server boundaries. Every formal parameter of a crossed call must be
`Val / Знач`; scalar defaults and omitted optional arguments are supported.
Non-Val parameters are rejected before argument evaluation. Arguments are
computed left to right in the caller; unsupported object values are rejected
before callee execution. Non-scalar results are rejected on return.

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
- Non-Val copy-in/copy-out and object serialization are required next parts of
  this direction, not optional edge polishing. They must not be implemented as
  ordinary live Python/BSL references. Copyback after an exception needs a native
  discriminator before implementation.
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

## Automated native witness (pending capture)

The ordinary existing `--client-probe` now includes the eleven positive scalar
observations. Its original four values remain first and unchanged. No workflow
flag, image, process timeout, credential boundary, manual dispatch, database
query or async runner changes are required. Literal managed-form client code
calls literal server methods, never `Execute(text)`.

Before the native invocation, the host runs the exact staged form source through
our interpreter in the existing bounded, credential-free isolated subprocess,
calling only `ВычислитьПробу()`. Its computed typed values must equal the finite
contract. The native marker independently must equal that same typed contract,
with nonce, client OnOpen wiring, source/module/roundtrip hashes, clean process
exit and quiescence checks unchanged. This establishes bounded source-bound
witness parity by equality to the same contract, not by trusting labels alone.
The native marker remains private under existing policy; the public report
retains verified completion and source identity, not unvalidated raw output.

The mixed template has a new exact hash. A narrowly checked inverse removes only
the appended witness and its one call, then verifies the original template hash
`4940e607de64f2ceae1ddd82f22b2b37e2156249451ce68de82b4bd49d37f328`.
All four existing parity adapters keep their original pins and produce identical
client-only modules. The separate PR90 async harness also touches this template;
any future merge must reconcile it explicitly and re-review the hash/inverse,
never relax either branch's source-binding rules.

Compile-negative and future-state discriminator modules remain separate planned
measurements, not fabricated captured evidence. Native positive results are
still uncaptured; a successful audited run on this exact source is required
before ready/merge. Local unit tests are not that result.

### Finite diagnostics after the first native run

The first native run reached the client entry and exited cleanly, with matching
source/module/roundtrip hashes, but rejected the completion marker. That result
alone does not distinguish a caught computation error from a typed value mismatch
and is not accepted directive evidence.

On rejected ordinary-client completion only, `marker_diagnostics` now reports a
finite phase (`invalid`, `error`, `completed`), mismatch class, zero-based value
ordinal (0–14, or 15 for excess values), and optional literal operation stage
(1–11). The BSL witness catches unexpected computation errors into a fixed
sentinel plus stage number, never error descriptions. Stage order is the eleven
labels in the positive probe; ordinal 4 is the first directive observation.
The original exact typed marker equality still rejects every sentinel, partial
result and mismatch. Metadata cannot grant success, export raw values or replace
source identity. The four old parity modules remain byte-identical.
