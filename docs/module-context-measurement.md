# Side-local module variables, not form state

Status: local implementation based on independently audited native capture
[run 39974330047](https://github.com/Atridis/yadinassi/actions/runs/39974330047).
Current implementation-head native parity and four-platform CI remain required
before ready/merge. The capture itself was a deliberately rejected measurement,
not a full parity run: later client suites and watchdog did not start.

## Evidence and scope

The [8.3.27 developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293)
§4.8.1.3 describes client module variables as lasting for the client form lifetime
and server module variables as lasting for one server call. The
[form-context tutorial](https://1c-dn.com/library/tutorials/practical_developer_guide_form_module_context/)
distinguishes module variables from form attributes. This interpreter supplies
logical side-local storage, not forms, form attributes, a database or network RPC.

The exact standalone scenario is `integrational_tests/directive_probes/module_context_core.bsl`.
Four direct client-to-server calls and one nested server call produced:

- Client initial: 10; server initial: 100; nested updated value: 111.
- Initially uninitialized server variable: true.
- Repeated outer call initial: 100.
- Escaping exception caught by client: true.
- Recovery initial: 100; recovery uninitialized variable: true.
- Retained client value: 11.

These are observations from 1C 8.3.27.1508 Linux/amd64, managed client, file
infobase, not predictions from the interpreter or universal claims about modes.
Fixture `module_context_native.json` binds all nine labels/values to source,
module, ZIP, run and tree. Artifact 12510512037 ZIP SHA256 is
`b7e993dda35cb8a0752dcb69f7de0357b7266ee481a25ea7c253ed0f65d34a39`.
Report commit `11b484a17304f90aa0c43ca50712406a4585c0b4` is the PR merge commit,
with ordered parents main `0dbb93818f9cf18e48aa0e493e86557ddd272c58` and head
`f8ada04bec5dd530b10a0999a87e0a8bd4c1b711`; its verified tree is
`187a9c15c8b627a49288f8be72c93cb26a34dbcd`.

## Standalone mapping

Top-level `&AtClient Var` and `&AtServer Var` (including Russian spellings) select
independent storage. Unannotated variables and unguarded root statements remain
client-side. Explicit server declarations never copy all client globals.

Each outer client-to-server call starts with fresh Undefined server slots, runs
its server initializer, then executes the routine. Nested server calls reuse
that activation. Both normal return and escaping exceptions discard it. Client
storage persists in its module owner. Initializers run before formal locals are
installed; an initializer failure does not copy out arguments. Imported modules
have independent owners, not shared process-global state.

Server initializer statements must be inside a conditional branch selected only
for the server and involving logical `AtClient`/`AtServer` symbols (or their
Russian spellings). The existing expression parser evaluates compound conditions,
`#Else` and `#ElsIf`; selection is not a textual rewrite. For example, both
`#If AtServer Then` and the `#Else` branch of `#If AtClient Then` qualify.
Generic `#If Server` alone retains the previous ignored-root contract. This is
an explicit standalone compatibility boundary, not native target-flag equivalence.
An initializer cannot replay unguarded root code or load imports. Client-only
comment import directives in server-selected root branches remain ignored, as
before; imports inside server routines remain rejected. Declarations
belong at module level, not inside initializer statement blocks. Nested conditional compilation can occur inside runtime If/loop bodies without
ending the enclosing initializer. Different client/server root fragments are
never joined to complete a partial runtime statement.

Server variable exports, module receiver access on the server, NoContext and dual
directives, form attributes and cross-context imports are not added. Client
variable exports retain their existing behavior. These missing core pieces are
not described as supported through this narrower module-variable feature.

## Strict parity and security gates

The staged BSL source is unchanged from the audited capture (SHA256
`a3e4fd9b809013b1d704a6a7af5b77353e04a129f3a0cd0ca3a40692458c1e17`).
The exact generated module and re-dump SHA256 is
`b74d71eadf523f443f47c86a12471d4e16bcfb6d82fa27738c346a3040ff3407`.

Temporary public `module_context` metadata is removed. Host preflight now runs
the entire staged source and independently computes all 119 typed values. Native
acceptance compares all 119 exactly: prior 109 plus the fixed module sentinel and
nine captured values. Changed initializers must fail the real interpreter gate.
No restored-source exception remains in host execution.

The exact three-part inverse (variable prefix, one call, helper/initializer suffix)
remains only for historical capture identity and four legacy parity adapters.
It restores the audited prior source byte-for-byte; all four generated adapter
modules remain unchanged. It is not a generalized directive stripper.

The private marker remains below 2048 bytes under compact, default and pretty
serialization; stage/report limits remain 8192/32768. Typed equality, nonce,
managed OnOpen/roundtrip, private-file reader, process and watchdog gates are not
weakened. Raw errors, paths and module values are not exported as diagnostics.
