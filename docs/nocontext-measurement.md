# Bounded NoContext measurement, not language support

This isolated measurement starts from audited main
`e83eb60f5b3aee19b774aa04e6c8286cbde48fa4` (tree
`5e0b0cb0047afb62ceff2530f772cfad52220021`). Runtime, parser and lexer are
unchanged: `AtServerNoContext` remains unsupported locally. No native expected
values are guessed. No ready/merge or full parity claim applies to this stage.

## Source and purpose

`integrational_tests/directive_probes/nocontext_core.bsl` contains six literal
client calls: four direct calls to an `AtServerNoContext` routine and two calls
to an `AtServer` wrapper which itself invokes that routine. A second NoContext
helper changes its scalar reference parameter. Explicit formal/local declarations
prevent accidental managed-form property bindings.

Fourteen observations, in source order:

1. normal.nested: nested result returned through the direct call.
2. normal.private: callee's modified Val parameter.
3. normal.server: independently compiled AtServer branch inside NoContext.
4. normal.caller: client non-Val value after normal return.
5. normal.val.caller: client Val value after normal return.
6. caught.matched: controlled exception handled inside NoContext.
7. caught.caller: client non-Val value after that normal completion.
8. escape.caught: caller caught the matching controlled exception.
9. escape.caller: client value after escaping exception.
10. context.normal.value: server wrapper's local value after a normal NoContext call.
11. context.escape.value: server wrapper's local value after a throwing NoContext call.
12. context.escape.caught: wrapper caught the matching controlled exception.
13. recovery.initial: subsequent direct call's input observation.
14. recovery.caller: client value after subsequent normal return.

All caller sink observations occur after the call or EndTry. Recording accepts
its value by Val and only appends it; it cannot modify the observed caller sink.
This distinguishes boundary transfer from same-side NoContext nesting without
repeating the previously measured object/alias matrix.

## Honest measurement protocol

The existing client form computes the original119 values first, then appends
`nocontext.core.v1` and14 observations. Native strict119 equality remains unchanged
and rejects the extra records. Only a complete exact119 prefix, exact sentinel,
exact134 total count and14 bounded values (Undefined transported as `U`, Boolean,
integer0..999) can yield the finite public `nocontext` diagnostic. Invalid or partial
vectors export no observations. Raw exceptions, strings, paths and objects never
enter the public diagnostic. Schema, nonce, source/roundtrip, process ownership,
quiet-exit and private-file checks stay active. Later client suites/watchdog are
not reached after this deliberate ordinary-probe failure; they must not be claimed
as passing in this measurement run.

Host preflight executes the **hash-restored original119 source**, not the new
NoContext helpers. The inverse removes exactly one pinned call and the complete
pinned helper block immediately before the unchanged module initializer tail, then requires the audited old source hash. A changed
helper or initializer fails the exact source gate. The four legacy parity modules
remain byte-identical to main. Native-only additions are not falsely presented as
local/runtime parity; after evidence-driven implementation this temporary capture
must be removed and replaced by strict whole-source native/runtime comparison.

The total is134 values (119 + sentinel +14). Private marker pretty-JSON majorant is2038
bytes, below the unchanged2048-byte limit. Production serializer bounds are8074/8192 wire bytes,31676/32768 late
summary,27714 early summary and14311/32768 provenance. The Async bound
also includes the longest14-value diagnostic, even alongside unreachable later
results. Caps are not raised and Async literal fixtures are unchanged.

## Remaining architecture discriminator

NoContext must have a distinct module-context capability, not just a server alias.
The official8.3.27 guide §4.8.1.3 forbids module-variable access and Var annotations
for NoContext; it permits calls to other no-context routines, not context-bearing
server methods. Dual NoContext will need independent compilation on each side.
AtClientAtServer belongs to command modules and is not claimed by this managed-form
capture. Primary source:
https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293

This first capture does not prove whether direct NoContext invocation runs the
server module initializer. A separate local preparation module uses an explicit
server initializer raising one controlled error and compares direct NoContext
with context-bearing calls. It cannot be appended to this119 module without
breaking its earlier context calls. Its runner/protocol still requires separate
review; it is not part of this capture or claimed as evidence. Compile-negative
cases likewise need an independently proved compiler classification; a modal
failure or generic process timeout is not compiler evidence.
