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
3. normal.profile: six independently compiled preprocessor flags inside NoContext.
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
`nocontext.core.v2` and14 observations. Native strict119 equality remains unchanged
and rejects the extra records. Only a complete exact119 prefix, exact sentinel,
exact134 total count and14 bounded values (Undefined transported as `U`, Boolean,
integer0..999, except the profile slot requires an exact integer0..63) can yield the finite public `nocontext` diagnostic. Invalid or partial
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

The total is134 values (119 + sentinel +14). Private marker pretty-JSON majorant is2035
bytes, below the unchanged2048-byte limit. Production serializer bounds are8071/8192 wire bytes,31673/32768 late
summary,27711 early summary and14311/32768 provenance. The Async bound
also includes the longest14-value diagnostic (False except the typed two-digit mask), even alongside unreachable later
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

## Audited first capture and one compiler-profile discriminator

Run [39992325017](https://github.com/Atridis/yadinassi/actions/runs/39992325017)
produced independently audited artifact12518806153, ZIP SHA256
`7505db8d495779ddf3ff012a7ab40927153cd953f0d088df4dc4861c0dd3238d`.
Head09dbc33a/treec597d5cc/sourceacebb0bf had the first14 vector
`[12,22,false,12,2,true,16,true,6,14,14,true,7,18]`.
The third value was a Boolean from `#If AtServer`: it was false. The remaining
observations establish this target's normal/caught copyout, suppressed escaping
client-boundary copyout, and retained same-server wrapper local changes after an
escaping NoContext call. This was rejected measurement, not full parity; later
client suites and watchdog did not run.

The v2 measurement changes only that third observation to a six-bit integer:
Client=1, Server=2, AtClient=4, AtServer=8,
ThickClientManagedApplication=16, ThickClientOrdinaryApplication=32.
Each bit has its own independent #If block, with no Else chain or assumed
relationship. The other thirteen observations and six direct call paths are
unchanged. The third slot rejects Boolean, Undefined and out-of-range values.
The versioned sentinel prevents the historical Boolean record being mistaken
for a new mask. The mask is not yet measured and no value is predicted.

The primary8.3.27 guide §4.8.1.2 enumerates the preprocessor keywords and includes
these six. It does not list AtServerNoContext/НаСервереБезКонтекста there;
§4.8.1.3 separately lists that name as an ampersand compilation directive.
No undocumented #If symbol is added, and documentation absence is not presented
as a native compile-negative experiment. Target compilation flags and runtime
logical side remain distinct; the first false AtServer bit does not mean this
server directive executed a client RPC or establish the other flags.

The separate unconditional-raising initializer preparation is not a validated
probe: it could fail at form construction before client entry. It is not included
or used as evidence. Initializer/context-access restrictions can follow explicit
primary documentation, clearly distinguished from measured facts; any future
native initializer probe must use a bounded observable effect, not startup failure.
