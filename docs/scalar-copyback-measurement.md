# Bounded scalar non-Val copyback evidence

Status: scalar measurement, implementation and strict parity passed independent
audit, PR92 checks and actual-main native run39951594654. The next
[object measurement](object-transfer-measurement.md) temporarily executes the
exact hash-restored scalar source, not whole-source object parity.
Root remains client-default. No database/query, network RPC, object transfer,
module-state transfer, NoContext, dual directives or async changes are included.

## Captured target and provenance

[Native run 39944524944](https://github.com/Atridis/yadinassi/actions/runs/39944524944)
measured 1C 8.3.27.1508 on the pinned Linux/amd64 image, file infobase (`/F`),
thick managed application. Its source head was
`4ab2f25c4fa834f97c3037b2b6723a2aeb283be5`, tree
`e8c8de8de369145d42c96d3474fa0a4b1d12a71c`.
Summary artifact 12497771050 has ZIP SHA256
`b5cc52786344468500083531e1a14daaf3415c0826fc58b402bdb5eaf92a606c`.
The exact staged source SHA256 is
`52d3dcb83a911f7219893b3705f77d2652e31557ebdfeabaf4384813d3cca07c`;
generated module and roundtrip SHA256 are
`285d66599e70ccd1f4ff6761bd9e171fef40dedd5cae3bdb05ce45f3a0b059cc`.
The captured values and labels are committed in
`integrational_tests/directive_probes/scalar_copyback_core.native.json`.
They come from that native artifact, not from interpreter-generated expectations.

Independent audit verified all 24 staged/trusted input hashes, nonce, tree,
module/roundtrip identities and every observation slot. Disputed calls are
literal calls from `&AtClient RunScalarCopybackProbe` to named `&AtServer`
routines, not local server wrappers. Caller sinks are read on the client after
return or after EndTry. The recording helper takes Value by Val and cannot
change the caller variables. Timing helpers intentionally change the actual
variable before server entry.

The measurement marker completed, but its extra records deliberately failed the
then-fifteen-value equality gate: witness_verified and client_probe.completed
were false. Later four client parity scenarios and watchdog were not started.
Thus this capture is semantic evidence, not a complete native acceptance PASS.
Previously observed preprocessing profiles were not remeasured here.

## Measured bounded semantics

The twelve operations cover assignment, Val control, return plus copyout,
server-caught and escaping exceptions, necessary repeated-actual discriminators,
one order-marked copy-in timing call, and recovery. The implemented subset is:

- Explicit named scalar non-Val actuals retain caller sinks while argument
  expressions are evaluated. Their values are read after all actual-expression
  effects; Val arguments retain their evaluation-time snapshots.
- Server formals are independent cells, not live caller references.
- On normal completion, every non-Val formal is copied out in parameter order,
  including unchanged values. The rightmost repeated actual therefore wins.
- An escaping server exception copies nothing back. A server-caught exception
  followed by normal completion does copy back.
- The result and every outgoing value must pass scalar validation before the
  first caller write. Unsupported objects cannot cause partial copyout.

This matches the captured independent-alias result 1, rightmost result 52,
unchanged/self-assigned/reverted right formal result 1, escaped caller values
1/2/3, and timing signature 192 with final X=9 and two helper calls.
Same-side reference behavior is unchanged. Property/index actuals, including
forwarded references, non-Val literals/expressions/omissions, object transfer and module state are not
supported by this bounded cross-context implementation. Objects and context
state remain mandatory subsequent work, not optional edge polishing.

### Explicit guide disagreement

The [official 8.3.27 developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1678862)
§4.7.4.3 describes changed-rightmost alias copyout and Undefined non-Val values
after an escaping server exception. It explicitly includes file infobases in
the interaction discussion. These predictions disagree with this audited target.
We implement the measured narrow target behavior, not an invented changed-only
model or an unsupported explanation that file mode resolves the discrepancy.
This does not establish behavior for every platform version or deployment.

## Accepted scalar strict parity after measurement (PR92)

The existing fifteen values remain unchanged. The literal `copyback.core.v1`
and all 34 captured scalar tokens now form an exact fifty-value contract in
both host and native validators. The host independently executes the entire
exact staged source in the real interpreter, with source hashes checked before
and after execution. It no longer strips a shared-source subset. Native success
requires the same exact typed values and existing source/module/roundtrip,
nonce, OnOpen, exit and quiescence checks.

Temporary public copyback metadata and its decoder are removed; no measured
value exception weakens acceptance. Finite failure diagnostics remain enums and
bounded ordinals only. The 2048-byte marker, 8192-byte wire and 32768-byte public
report caps are unchanged. The four legacy parity adapters still restore their
exact historical template and produce byte-identical modules. PR90 integration
must reconcile template pins and independently verify combined serializer
headroom; this branch does not modify that async branch.

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

The complete bit alone is not a parity claim. The scalar fifty-value gate passed
independent native audit. Each subsequent implementation still requires current-head
parity, full regression tests, four-OS CI and independent artifact audit.
