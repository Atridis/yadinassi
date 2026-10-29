# Bounded native tree profile

`tree-v1` is a separate, immutable **FillValues measurement profile**, not a
replacement for the six-scenario native regression suite and not a claim that
FillValues is implemented. Its single source is
`integrational_tests/measurements/tree_fill_values.bsl`. The source hash, 33-record
count and finite observation grammar are explicit. Later Copy/Sort measurements
must use a new explicit profile/version rather than silently reinterpret accepted
FillValues evidence.

The existing collections source and its 1023 records are unchanged. The new lane
uses a separate invocation, wire schema, report purpose and artifact. Ordinary
six-scenario success and tree-profile success are separate required obligations
before accepting a runtime implementation. A valid native measurement may disagree
with the interpreter; measurement validity is not runtime parity or merge readiness.

## Execution and source identity

The same isolated native-image/bootstrap gates create the disposable base and
named test user. Only the fixed `--tree-suite --invocation-nonce` route admits this
profile. Mixed legacy client/parity flags, unknown profiles and invalid nonces are
rejected. The 21 staged sources include the profile helper, observation contract,
original BSL source and original client template. Source hashes bind every staged
input, and the stage rechecks the complete inventory after execution.

The server invocation runs the original BSL source through the existing launcher.
The separate managed-client adapter is hash-bound to the original source and
current client template. It adds client directives, captures only the two existing
message calls and wraps the original top-level calls; its inverse verifies that
all original source text is recovered. No action result, mutation state or expected
native answer is substituted by the adapter. Roundtrip module identity, entered
and completed markers, fresh nonce, process exit, process census and strict
server/client byte equality are required.

## Bounds and failures

Native output is capped at 8192 bytes. Before storing each managed-client record,
the capture routine accepts only ASCII letters, digits and the fixed punctuation
space, hyphen, dot, colon, square brackets and underscore. It reserves one LF per
record and enforces the exact 33-record bound. The tree-only adapter explicitly
uses the already-established no-linebreak JSON writer settings; it does not rely
on the historical template's default formatting. Its guarded inverse leaves
ordinary client adapters unchanged. The independent contract validates
the complete 6017-byte valid-output grammar; unexpected values or observer failures
are not accepted as ordinary action exceptions. The inherited private stage-report
cap remains 8192 bytes, public report cap 32768 bytes, and this lane's transport cap
is 65536 bytes. None of the old six-scenario caps is raised.

A rejected observation can report only a closed diagnostic: server/client site,
case ordinal, a finite category and an optional calibration-stage symbol. Raw
invalid output and native exception messages are never exported. The finite
categories distinguish malformed transport, calibration failure, probe B/P/Q/R
and unsupported payload structure. Such a diagnostic never grants observation
validity or permits artifact export.

Local synthetic adapter, negative-contract and transport tests do not establish
1C semantics. Native source-bound acceptance must be recorded separately after
the dedicated lane actually runs, and later runtime parity requires independent
interpreter execution against that same native capture.
