# Bounded dual NoContext implementation

This slice supports `&AtClientAtServerNoContext` and
`&НаКлиентеНаСервереБезКонтекста` as independently compiled client/server variants.
Root and unannotated routines remain client. A dual call inherits execution side,
not module capability: both variants have no module context. The interpreter is
still autonomous; no forms, database/query, network RPC or command-module
`&AtClientAtServer` support is added.

## Audited target evidence

[Measurement run40016529386](https://github.com/Atridis/yadinassi/actions/runs/40016529386)
on head `d8cf849b69f666bf1d35f061879232f345d55bfa`, tree
`b7b8bf0b2a0ebc2fd5ff0a87eb87d9c10127f8c2`, was independently audited. The
checkout was synthetic merge `86fe6545aabe331826dfb52d336537db405a8e34` with that
same tree. Summary artifact12527973799 ZIP SHA-256:
`7dd804a26fb5cf63cf5de93c2dc1ba908767bba9f64e949f04626344d9278dba`.
The literal managed-form source SHA-256 was
`9ce132a3edef0c944a9a2d6776f98d1f209ecbd57ae314e8f02ba4e56d23ae06`;
generated module and native roundtrip were
`029fc7c47c32e8cc494b2dfb4256b83a7be02836403143e08542edce5b0c90c3`.
Pinned target: Linux/amd64, 1C8.3.27.1508, managed application, file infobase.

Nine ordered observations were `[3,32,17,3,17,41,3,32,17]`:

1. Client: profile, Val Array/returned-reference alias, escaping scalar write.
2. Context server: profile, escaping scalar write, caller module-state recovery.
3. NoContext server: profile, Val Array/returned-reference alias, escaping scalar.

Each caller invokes the named dual routine directly. The outer server wrappers
are genuine client-to-server boundaries, but their observations occur on the
server before the arrays return. The controlled exception is checked; unexpected
errors are rethrown. Alias32 and scalar17 distinguish ordinary same-side reference
behavior from packet-copy/normal-only-copyout. Caller state41 establishes recovery,
not a native negative test for access from inside the dual routine.

All three captured profile masks3 mean generic `Client` and `Server` true,
logical `AtClient` and `AtServer` false. This is a target-specific compiler
observation, not universal target equivalence or permission to change standalone
defaults. The final source projects only logical bits, producing masks0 and
preserving the other six measured observations. Exact source reconstruction binds
that projection to the captured fixture. A fresh final-source native run is still
required; the historical capture was deliberately rejected by strict134 and did
not run the later full-client lanes/watchdog or establish full parity.

## Runtime and compiler contract

Dual variants are compiled independently using their side's existing standalone
target defaults; both logical At* flags are false. There is no new preprocessor
symbol. Variant identity retains the original declaration's token provenance.
Only variants of that same declaration can share a name; conflicting declarations
are rejected before effects. Persistent replacement removes the previous whole
family. A missing selected-side variant fails before argument effects, rather
than falling back to the other side or a host function.

A matching dual call never switches side, creates a server activation, serializes
parameters, or replays a module initializer. Ordinary non-Val references, Val
object handles and writes surviving an escaping exception are preserved. An
explicit call from a client dual variant to `AtServerNoContext` remains a real
logical client/server crossing with the existing bounded packet contract; its
server counterpart is a same-side call.

Module variables, implicit ThisObject/ЭтотОбъект and context-bearing callees are
unavailable. Module-storage reads/writes through an explicitly passed module
receiver are also denied by this bounded capability policy. Already bound
references deliberately supplied by a context-bearing caller, including a module
field reference, retain ordinary parameter semantics; they do not expose a module
handle for fresh field resolution. Ordinary object arguments and explicit
local/formal shadows remain legal. Execute/Eval cannot
restore capability. Entry/exit uses task-local side/capability stacks and finally
cleanup; synchronous dual calls around Await must not leak state between tasks.
The existing NoContext no-initializer-replay policy remains an explicit autonomous
boundary, not a measured promise about every native initialization side effect.

`Export` may decorate an internal dual declaration, but invoking dual routines
through an interpreter module receiver, including imported or stored receivers,
is outside this initial autonomous subset and is rejected. This receiver boundary
is not a claim about all native common-module import mechanisms. The platform
form-module rule specifically excludes exposing such routines via ThisObject.

Dual-on-Var, Async dual and Await in a dual body remain rejected. Async-dual
legality has not been measured; the initial rejection is a conservative supported
subset, not an assertion of universal native illegality. Context-bearing dual
`AtClientAtServer` remains unsupported. No intentionally uncompilable native
fixtures or new compiler-error-classification infrastructure are added.

Primary references: [8.3.27 Developer Guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293),
§4.8.1.3 for form/command directives, module visibility and ThisObject exposure;
[preprocessor reference](https://1c-dn.com/library/preprocessor_instructions/) for
target versus logical compilation flags. Positive observations do not replace
unperformed native capability-negative or Async-dual legality tests.

## Strict source-bound acceptance

The final contract has135 values: the preceding134 plus ONE fixed token
`dual.v1:` followed by nine three-digit ASCII integer fields. The projected vector
is `[0,32,17,0,17,41,0,32,17]`. Native and host must match the entire exact typed
contract. The dense encoding is retained to respect the unchanged2048-byte private
reader cap, not as a capture-only success exception. Original JSON writer and all
security/transport caps remain unchanged; no new writer settings or enums.

Temporary public dual diagnostic payload is removed. Host preflight executes the
entire exact staged source, including dual calls, without stripping the new body.
The exact inverse remains only for constructing the four unchanged historical
adapter modules. Existing Async8 bodies/identities and source-bound comparison are
preserved. Full local tests, current-source native strict135, independent artifact
audit, fresh same-run Async8 composition evidence and required OS CI gate release.
These gates are pending for this implementation, not satisfied by measurement-only
history or tests of the parent runtime.
