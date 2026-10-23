# Side-local module-variable capture, not form state

Status: measurement-only, based on audited main
`0dbb93818f9cf18e48aa0e493e86557ddd272c58`. No new runtime behavior is implemented.
The existing 109-value object/scalar witness remains unchanged and strict native
acceptance intentionally rejects the nine extra observations. This Draft must
not be readied or merged as measurement-only work.

## Primary-source boundary

The [8.3.27 developer guide, §4.8.1.3](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1808293)
describes client module variables as lasting for the client form lifetime and
server module variables as lasting for one server call. It forbids NoContext/dual
annotations on variables. The [form context tutorial](https://1c-dn.com/library/tutorials/practical_developer_guide_form_module_context/)
distinguishes module variables from form attributes. We therefore do not copy
client globals into server state or implement forms, databases or network RPC.
Unannotated standalone root/variables must remain client-default. The standalone
mapping of explicitly server-only initializer statements is not yet implemented.

## Nine observations from four direct calls

`integrational_tests/directive_probes/module_context_core.bsl` explicitly declares
one client variable and two server variables before all routines. Side-guarded
module-body statements initialize client/server counters at the end of the module.
Four literal client-to-server calls, including one controlled escaping exception,
and one nested server helper observe:

1. Client counter before any call.
2. Server counter at entry, before mutation.
3. Nested server helper sees and updates the same counter.
4. The uninitialized server variable is Undefined.
5. Counter entry on a separate call.
6. Escaping error is caught and matches a fixed local sentinel.
7. Counter entry after the escaping error.
8. Uninitialized server variable after the escaping error.
9. Client counter retained after all calls.

All constants are stimulus, not expected native values. No runtime/native model
is inferred until capture is independently audited. Unexpected top-level failure
uses the existing error-phase contract; partial records never become public
observations. Every new temporary is explicitly declared or a parameter. The
finite list permits only exact Boolean, integer 0..999 or the fixed Undefined
encoding, never objects, paths or raw exception text.

## Exact source and unchanged acceptance

The native template adds an exact module-variable prefix, one call and a suffix
containing mechanically adapted helpers plus side initialization. Its inverse
requires the full new source hash, exact prefix/suffix and exactly one call;
restored bytes must hash to the audited source
`6e29d85372e623c412e0662ad7514fbc76963fb5bd42bde6a100a4b5c7a2b120`.
Host preflight executes this restored 109-value source, not the new variable
scenario. The entire staged native source is still hashed before and after.
The four historical parity adapters independently retain their original bytes.
No generic directive stripping or runtime success claim is involved.

Native accepts only the original 109 values. Temporary public `module_context`
metadata is allowed only on failed/completed/count/ordinal109, after exact typed
matching of the whole prefix, fixed sentinel and all nine finite records. A
malformed or partial list is never exported. Existing nonce/schema/quiet/exit,
module roundtrip and watchdog gates remain unchanged.

## Bounded serialization and next step

The fixed 109 prefix plus sentinel and nine maximum-width false observations
is 119 marker values: compact 1,257, default 1,384 and pretty 1,876 bytes, below
2,048. Reachable ordinary-client failure serializes to 6,838 bytes below 8,192;
unit tests prove that later clients/watchdog do not run after that failure.
Conservatively preserving every audited actual-main public report field plus
this failed observation metadata is 25,129 bytes including a newline, below
32,768. This last synthetic shape is budget evidence, not an accepted report.
No caps are raised. Future Async integration requires a separate combined proof.

After native evidence: decide the bounded server-initializer AST mapping, then
implement separate side variable registries and outer-server activation lifetime,
with nested reuse and cleanup after normal/exceptional completion. Retain default
root client and existing client exports; do not infer support for server variable
exports, wrong-side accesses or form attributes. Separate compiler-negative
scenarios may check unsupported annotation/visibility without contaminating this
positive module. Replace temporary capture with strict whole-source parity before
ready/merge. Current Async branch/runtime work remains isolated.
