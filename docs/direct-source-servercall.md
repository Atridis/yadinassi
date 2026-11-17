# Direct source qualified ServerCall (bounded)

The python-direct source host can call an exported synchronous contextual routine
through a qualified, server-only CommonModule with `ServerCall=True` and
`ReturnValuesReuse=DontUse`. Every formal parameter must be `Val`. Defaults may be exact immutable scalar
literals: Undefined, Boolean, String or Decimal.
This is a logical source-host boundary, not a native server or full 1C parity claim.

Admission checks the actual client caller, current application/module metadata,
registered origin, declaration and generated plan, lifecycle, and canonical host
registrations before argument effects and again before entering the server.
Custom origin host registrations are explicitly rejected, not silently discarded.
Async, dual, NoContext, reuse, by-reference parameters and nonliteral defaults
remain outside this slice. Same-side behavior is unchanged; the logical-side host entry is not
widened.

Named Val actuals are read after all actual argument effects. The complete bounded
packet is copied before entry using the existing direct server transfer contract.
Default parameter/node/value identities are captured during source compilation and
revalidated before and after actual effects. Explicit holes and missing trailing
arguments are filled with those immutable values on the caller side before packet
copying. The generated callee receives a complete argument list and does not
execute a default expression. Required holes are rejected before actual effects;
unary expressions (including negative literals), collections and date/Null defaults
are deliberately not added to this slice.
A new exact source interpreter owns fresh registries and empty module storage.
Its scoped origin seal is separate from the application module registry; private
helpers use that seal while nested/global modules retain their existing admission.
The source application, family, compilation profile and target remain the same.

Safe-mode and active-transaction transfer guards apply. Server activation runs with
transaction admission disabled; nested same-side calls cannot widen it. Generated
plans execute without VM routine dispatch. A complete copied result must validate
before returning. All exits revoke the seal, close the activation and restore the
caller side/module stacks. There is no copyback in this slice.

`test_python_direct_source_servercall_no_vm` replays supported existing ServerCall
cases with legacy execution and routine dispatch poisoned for the entire test.
Security regressions cover argument-time origin mutation, late named values,
packet cycles, detached outputs, safe mode, transaction boundaries, custom host
registrations, constructor hooks and expired activations. Existing unsupported
source-wide cases remain reported separately; this is not a green-full-suite claim.

Scalar ServerCall reuse is separately admitted under the closed contract in
`direct-source-server-reuse.md`; its no-default scalar constraints do not widen
the ordinary DontUse transfer profile.
