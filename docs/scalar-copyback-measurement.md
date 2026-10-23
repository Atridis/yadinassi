# Bounded scalar non-Val copyback measurement

Status: measurement-only, uncaptured. No non-Val runtime support is claimed.
Root remains client-default; no database/query, network RPC, object transfer,
module-state transfer, NoContext, dual directives or async changes are included.

## Why capture first

The [official developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1678862)
§4.7.4.3 describes independent argument copies, Val suppressing copyout, the
rightmost changed formal winning for repeated actual variables, and Undefined
copyout after an escaping server exception. “Changed” and exact copy-in timing
still need evidence for this target. Do not guess assignment tracking versus
final-value comparison from documentation alone.

The twelve operations cover common non-Val assignment, Val control, return plus
copyout, server-caught and escaping exceptions, independent repeated actuals,
rightmost changed/unchanged formals, B=B, B=2 then B=1, one order-marked copy-in
timing call, and recovery. This is not an exhaustive defaults/parentheses matrix.
Object transfer and context-bearing module state remain mandatory next work.

## Existing bounded protocol

The ordinary client probe retains its original fifteen values. It appends the
literal `copyback.core.v1` followed by 34 scalar ValueToStringInternal tokens in
the order below. The standalone source prints labels; the managed-form adapter
returns only ordered tokens, so no Message dialogs or raw exception text escape.
The original strict fifteen-value native acceptance is unchanged: extra records
always reject success. No synthetic result becomes a native fixture.

Failure diagnostics accept the extension only for a valid completed marker with
exact nonce/schema/witness/key set, exact count/sentinel, and every token in the
finite domain Undefined, Boolean or integer 0..999. The public `copyback` list
contains only JSON null, Boolean or bounded integer values. Unknown token,
partial capture, arbitrary string, malformed JSON, wrong nonce or oversize file
never exports the extension. The existing 2048-byte private marker bound remains.
These are observations, not expected parity values.

A conservative six-client codec fixture with maximum-size output counters,
full process diagnostics and 34 false values round-trips through the real stage
serializer in 8169 bytes (8192 cap); its compact named report is 11201 bytes
(32768 cap). This is not a blanket bound for combining future metadata. The
real measurement fails in the ordinary probe before later clients run. PR90
integration must separately re-prove combined wire/public-report headroom; do
not raise caps or silently drop diagnostics. Capture-only payload is temporary.

The independently audited actual-main public report serializes to 24745 bytes
with the production indent=2/sorted-keys serializer. Retaining every original
field, adding the maximum 34-false capture, and setting the ordinary probe to
failed/invalid_result/witness_verified=false yields 25596 bytes, below the
32768-byte public cap. This is a conservative serialization shape, not a valid
accepted report or new native evidence.

The host preflight uses an exact full-template hash-bound inverse to remove only
the appended capture suffix and one call block, then checks the restored source
SHA256 `b98f7cb8e3489fabdd5df6cec8b929b7e059f9931f1fbfedb8d112be53c1f437`.
It computes the already audited shared witness, not native-only copyback helpers.
The original staged-source hash is checked before/after. The four legacy parity
adapters independently restore the exact old template and retain byte-identical
modules/pins. Source/module/roundtrip, nonce, OnOpen, exit and quiescence gates
are unchanged. No PR90 files or workflow/image pins change.

## Observation order (zero-based)

- 0: `entered`
- 1: `success.error`
- 2: `success.value`
- 3: `val.error`
- 4: `val.value`
- 5: `function.error`
- 6: `function.result`
- 7: `function.value`
- 8: `caught.error`
- 9: `caught.matched`
- 10: `caught.value`
- 11: `escaped.caught`
- 12: `escaped.matched`
- 13: `escaped.value`
- 14: `escaped.untouched`
- 15: `escaped.val`
- 16: `alias.independent.error`
- 17: `alias.independent.second`
- 18: `alias.independent.value`
- 19: `alias.rightmost.error`
- 20: `alias.rightmost.value`
- 21: `alias.unchanged-right.error`
- 22: `alias.unchanged-right.value`
- 23: `alias.self-assignment.error`
- 24: `alias.self-assignment.value`
- 25: `alias.reverted.error`
- 26: `alias.reverted.value`
- 27: `timing.error`
- 28: `timing.signature`
- 29: `timing.value`
- 30: `timing.calls`
- 31: `recovery.error`
- 32: `recovery.value`
- 33: `complete`

A true complete bit means execution reached the final record, not that semantics
matched a prediction. Entered/complete and per-operation errors must be audited
before interpreting values. Current runtime still rejects non-Val boundaries;
local execution tests only verify that this guard remains, never native parity.

## After capture

Audit exact source/tree and all records, then implement the measured common
scalar copy-in/copy-out model with detached formals and explicit caller sinks.
Only after that replace the measurement-only exception with independently
computed exact-source runtime/native parity. Full unit/CLI/four-OS CI and audited
native evidence remain required for implementation ready/merge. No implementation
or semantic broadening follows from a merely completed measurement marker.
