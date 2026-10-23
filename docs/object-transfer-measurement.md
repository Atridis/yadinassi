> Current status: the historical measurement stages below are superseded by the
> implemented narrow contract and strict whole-source parity described at the end.
> Their rejected measurement runs are evidence of observations, not acceptance.

# Bounded object-transfer measurement

Status: uncaptured measurement-only stage on exact main
`429674b02a0f220a879ab4daf86234c03e5ee54c`. No object-transfer runtime
support or native expected object observations are claimed. The scalar stage's
strict 50-value witness passed native run
[39951594654](https://github.com/Atridis/yadinassi/actions/runs/39951594654)
and independent actual-main artifact audit. This extension deliberately rejects
ordinary-client acceptance until its observations are audited and implemented.

## Scope and protocol

Eight literal client-to-server calls and 48 fixed primitive observations cover
mutable Array/Structure graphs with Number leaves, a shallow repeated-child
graph, normal and exceptional completion, Val, return/out-param relationships,
and mutable actual-expression timing. Boolean/Undefined observations are flags
or unavailable readings. There is no object-equality oracle, arbitrary graph
serializer, cyclic input, database/query, module state, NoContext, dual directive
or Async change. Module state remains separate mandatory next work.

Standalone source `integrational_tests/directive_probes/object_transfer_core.bsl`
is SHA256 `9fae5ac7a0a7dc243a65cb124247629cbc04ee7130ab169c1d61933cbbc9d33f`.
The integrated adapter keeps all operations/calls in place. It changes the
client entry to return a local record array and its recording sink, and adds
root-local finite stage assignments plus an outer failure catch (below). Standalone
Message emits typed diagnostic strings; native integration avoids dialogs and
records Number/Boolean directly, or the fixed string `U` for Undefined. This
bounded encoding is not a native semantic expectation. Root remains client.

The existing fifty values are unchanged. The literal `object.transfer.v1` and
48 measurements are appended. Strict native equality still rejects the extra
records; neither complete flags nor diagnostic metadata can grant success.
The finite decoder exports `object_transfer` only after the first fifty values
match exactly by type/value and nonce/schema/witness/key/count/sentinel checks
pass. It accepts only Boolean, integer 0..999, or the exact private `U` token
(mapped to JSON null publicly). Arbitrary strings, floats, negative/large
numbers, wrong baseline, partial/malformed/oversize markers export no list.
The public list is fixed length 48 and permitted only for the failed count
classification at ordinal 50, never success or another mismatch.

During this measurement, host preflight executes the exact hash-restored scalar
source SHA256 `52d3dcb83a911f7219893b3705f77d2652e31557ebdfeabaf4384813d3cca07c`,
not the appended object operations. The inverse requires the complete new
source hash, unique exact suffix/call blocks and exact restored hash. Original
staged source is checked before/after execution. Four old full-client adapters
restore their exact historical template and remain byte-identical. Source,
module/roundtrip, process, nonce and security gates remain unchanged.

## Fixed bounds, not increased caps

A maximum-length admitted 48-value primitive capture gives compact/default/
pretty JSON marker sizes 1275/1382/1794 bytes, below the unchanged 2048 limit.
Keeping ValueToStringInternal strings instead would have exceeded that bound
under pretty formatting; the explicit primitive encoding avoids that assumption.

Ordinary-client rejection occurs before the four later client runs and watchdog,
so those records remain not_started. The exact production stage serializer with
maximum case counters, full ordinary-client process diagnostics and 48 false
values is 7072 bytes, below the unchanged 8192 cap; both decoders roundtrip it.
Tests verify the execution ordering, not merely a hand-built budget claim.
A synthetic combination with all later client records populated plus this
capture is unreachable and is not claimed to fit. The existing actual-main
public report, retaining every field and adding the maximum capture with failed
ordinary-probe flags, serializes to 25869 bytes under the production pretty
format, below 32768. This is a conservative shape proof, not an accepted report.
PR90 integration must separately reconcile pins and combined metadata budgets;
this isolated branch does not change PR90 or increase any cap.

## Interpretation and next implementation

The official [8.3.27 guide, section 4.7.4.3](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1678862)
describes independent formal copies and duplicated occurrences of the same
nested object. It also contains alias/exception rules contradicted by the
scalar target capture. Therefore neither guide predictions nor Python deepcopy
are used as native expected object results. Mutations distinguish identity;
readings of contents alone cannot prove alias preservation or root replacement.

Capture on the pinned 8.3.27.1508 Linux/amd64 managed thick/file target, independently
audit every observation and source path, then select the bounded transfer model.
An implementation must build/validate all outgoing graphs before caller writes,
reject unsupported leaf types/cycles under bounded traversal, and never pass
live References or host/module objects. Remove temporary metadata and restore
exact whole-source strict parity after implementation. Full CI/native audit are
required before ready/merge; a measurement-only failure is never ready evidence.

## Eight operations and decisions

1. **Val mutation/rebind (1-4).** Mutate the Structure and nested Array, then
   rebind the formal. Observe caller fields and a retained child alias. Determines
   graph isolation rather than merely suppression of caller-variable assignment.
2. **Independent formals (5-10).** Different caller variables initially alias
   one graph. Mutate the first formal, read the second, then mutate the second.
   Record both returned leaves, mutate the first caller graph and read the second
   plus the retained original child. Determines per-formal input copies, caller
   output aliasing and separation from unpassed aliases.
3. **Repeated sink (11-14).** Pass the same caller variable twice, change only
   the first formal and return the untouched second formal's reading. Determines
   how independent inputs and unchanged-right copyout interact for objects.
4. **Non-Val root rebind (15-18).** Assign a fresh Structure/Array graph to the
   formal. Observe caller fields and the N field of an unpassed old root alias.
   This old-root observation distinguishes replacement from in-place root merge;
   a retained child alone would not distinguish those two implementations.
5. **Nested graph and function result (19-27).** One Structure initially has
   the same Array at Left and Right. Server mutates Left and reports Right,
   explicitly restores Right = Left, then returns the same root it copies out.
   Client mutates the out-parameter graph, records sibling/result readings, then
   mutates the result and records sibling/out-parameter readings. Determines
   incoming repeated-child treatment, outgoing repeated-child treatment and
   sharing across return/copyout roots independently.
6. **Escaping failure (28-36).** Mutate a non-Val graph and a Val graph, rebind
   the non-Val formal, leave another non-Val graph untouched, then raise a fixed
   error. Record caught/matched flags, explicit Undefined flags and safe scalar
   readings from destinations/retained aliases. Determines failure publication
   and leaked mutations without assuming scalar exception behavior extends to
   objects. No raw error descriptions enter output.
7. **Mutable snapshot timing (37-42).** Earlier Val X and later non-Val X precede
   a client actual-expression helper that mutates the old graph, rebinds X, and
   increments a call counter. Determines whether Val captures a graph immediately
   or retains its handle until serialization, and tests the late non-Val read.
8. **Caught recovery (43-46).** Server mutates a graph, catches its controlled
   exception and returns normally. Determines normal publication after a caught
   exception and recovery after the earlier escaping call.

Each operation has one `.error` Boolean. For independent-formal and graph
operations it also covers required client mutation checks; if true, their partial
readings are not a completed semantic observation. `escaped.error` means the
client caught an exception, while `escaped.matched` identifies the controlled
probe error. `complete` means only that recording reached the end, never parity.

Readers verify the Structure/Array type, property presence and nonempty Array
before dereferencing. A missing/unexpected/out-of-range numeric reading becomes
Undefined. This is not an alternative success condition. Native acceptance must
eventually compare every audited typed record, not just error/complete flags.

## Exact zero-based record order

```text
00 entered
01 val.error
02 val.root
03 val.leaf
04 val.retained
05 independent.error
06 independent.server.second
07 independent.x.before
08 independent.y.before
09 independent.y.after
10 independent.retained
11 repeated.error
12 repeated.server.second
13 repeated.leaf
14 repeated.retained
15 rebind.error
16 rebind.root
17 rebind.leaf
18 rebind.retained
19 graph.error
20 graph.server.sibling
21 graph.x.sibling
22 graph.result.left.after.x
23 graph.result.right.after.x
24 graph.result.sibling
25 graph.x.left.after.result
26 graph.x.right.after.result
27 graph.retained
28 escaped.error
29 escaped.matched
30 escaped.value.undefined
31 escaped.value.leaf
32 escaped.retained.root
33 escaped.retained.leaf
34 escaped.untouched.undefined
35 escaped.untouched.leaf
36 escaped.val.leaf
37 timing.error
38 timing.early
39 timing.late
40 timing.caller
41 timing.retained
42 timing.calls
43 recovery.error
44 recovery.matched
45 recovery.leaf
46 recovery.retained
47 complete
```

## Evidence and validation limits

The official guide's independent-copy and repeated-child examples motivate these
discriminators, not expected results. Its changed-only copyout and escaping-error
predictions already disagree with this project's audited scalar target.

- [Official 8.3.27 guide, section 4.7.4.3](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/?sphrase_id=1678862)
- [Official Val/Array transfer guidance](https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Clients/Optimizing_client_server_applied_solutions_for_SaaS_application_delivery_model/?language=en)

Local checks must distinguish syntax/mechanics from native evidence. The current
interpreter should parse/install the complete source without output; running the
literal entry should record eight unsupported-object call errors and still emit
all 48 records. An in-memory-only replacement of AtServer with AtClient can test
the bodies and observer mechanics, but it removes the boundary and is explicitly
NOT native or cross-context semantic evidence. Never save that transformed output
as a native fixture.

Capture still requires target/version, complete private primitive records,
source/module/roundtrip hashes, nonce, compiler phase and independent audit.
Do not weaken the existing strict 50-value acceptance gate or enlarge marker/wire
caps. Measurement is not an acceptance PASS. After a measured implementation,
require exact whole-source host/native parity and existing release gates. PR90
and its integration source/hashes remain untouched by this preparation.

## First capture and finite failure localization

[Run39956179492](https://github.com/Atridis/yadinassi/actions/runs/39956179492)
reached client entry and exited quietly with exact source/module roundtrip, but
reported an error-phase marker and no object observations. Summary artifact
12503210246 has SHA256
`bc4805c5052cb3278acacaa1b2c4419ee112b709cefd1aec31000a4a0da2a31a`.
This is not the planned completed-count capture and establishes no object
transfer semantics or exact error cause.

Source inspection found implicit helper variable `Items`, a native managed-form
property name. The existing collections adapter already explicitly localizes
that collision. All new object helper temporaries and generated probe locals
are now explicitly declared with Var, not renamed one collision at a time.
A static AST check rejects undeclared assignment targets throughout all sixteen
measurement routines. This prevents unintended form bindings; it does not prove
that the earlier error came from that particular assignment. Runtime is unchanged.

The integrated root also tracks a local finite stage before each original
executable root statement. The exact mapping is committed in
`integrational_tests/directive_probes/object_transfer_stages.json`, bound to the
standalone source hash. Stages1..123 identify caller statements; stage0 means
root setup. An outer catch discards all partial records and returns only the
fixed `object.runtime-error` sentinel and stage. It never exports raw error text
or relies on scalar copyback from a throwing helper. A helper callsite stage
does not establish the failing inner operation.

Only the exact already-matching fifty-value prefix plus this two-value sentinel
can yield public `object_error_stage` metadata. It is a bounded integer0..123,
mutually exclusive with the48-value observation list, and valid only for a
failed completed/count/ordinal50 classification. Strict acceptance still rejects
it. Known-stage, invalid-type/range, partial-list suppression and injected root
setup/observer failures are tested. The full observation branch and all caps
remain unchanged; no new diagnostic infrastructure or native expectations exist.

## Audited capture and one architecture-essential timing discriminator

Run [39958307601](https://github.com/Atridis/yadinassi/actions/runs/39958307601)
produced the complete original 48 observations. Its summary artifact12502983241
has SHA256 `ac9a2bf09ee04e7294856eff9688e5e02952e1f8fe827271dbda3bb06ee1e209`.
Independent audit verified all319 source blobs,24 staged hashes, runtime provenance,
module/roundtrip identity, nonce/schema, shared-source host50 and six unchanged
server cases. Report PR merge commit `cc1e9aacd33cf92162463ed4f782b427687cc275`
has the same tree `4644b555cb9f2e3e78226063a2303d243eb2e7da` as head90f797ee.
This was measurement only: marker phase completed, but validation completed=false,
witness_verified=false; later client parity and watchdog were not started.
Explicit locals removed the earlier failure in this run, without proving its
particular cause.

The original timing call observed named Val Early=73, non-Val Late=73, caller=73,
retained old graph=72, Calls=1. The preceding scalar timing used an expression
result for its first Val argument, so it did not settle named-Val timing.
One additional direct client-to-server call now distinguishes named object,
retained object alias, object expression result, named scalar and scalar expression
result before a final argument mutates the old object and rebinds both caller
variables. Ten additional primitive observations include caller/retained state and
an exactly-once counter. No native expected values are guessed for this new call.
The original48 labels and operations remain in order, including their completion
label at ordinal47; the new labels occupy48..57. The new suffix is not interpreted
as completed evidence unless all58 records pass the finite decoder.

This section supersedes the earlier measurement counts: nine server operations,
19 explicitly localized routines,58 observations,109 total marker values including
the unchanged strict50 prefix and one sentinel. Source-bound root stages now span
0..141. The private marker maximum is1335 bytes compact,1452 default and1904 pretty,
under the unchanged2048 limit. The reachable failed-stage wire test is7132/8192.
Conservatively retaining every old actual-main public field while adding all58
worst-width values gives26059/32768 bytes; that synthetic shape is a serialization
budget proof, not an accepted report. The strict50 acceptance gate, shared-source
inverse, four historical client adapters, runtime and all caps remain unchanged.
A separate Windows-only pure request-binding test uses the existing portable
fixture reader, so binding negatives are exercised rather than accidentally
passing through descriptor/path identity rejection. Production secure reads are
unchanged; the precise differing Windows stat field was not captured.


## Implemented contract after independently audited mixed capture

[Run39961116549](https://github.com/Atridis/yadinassi/actions/runs/39961116549)
produced all58 observations. Artifact12504562952 ZIP SHA256:
`2f552e2620500c68823da3bba8bc06c3d9d9e082ca21d5bbfe0966d1404498ba`.
Head `fadda0be4f066abaaf7d9c6a786fd4901aef3be0` and report PR merge
`174795833b33a3e9061c37efb9928e2fbab463ae` share tree
`182383962308f3f5810b593382956c28d5ce3549`. Independent audit verified all319
blobs,24 pins, runtime provenance, source/module/roundtrip, nonce/schema and
original48 equality. The ten appended values were false,73,72,72,74,11,73,74,72,1.
The historical strict50 gate intentionally rejected extras; later client/watchdog
phases did not run. This does not count as strict runtime/native acceptance.

The measured implementation reads named caller storage after all argument
expression effects, for both Val and non-Val. Expressions evaluate once in order;
scalar expression results retain their scalar value, while object expression
results retain the old object handle and therefore see intervening mutation before
serialization. Every Array/Structure occurrence is copied separately, including
shared child occurrences, repeated formal inputs, outputs and returned roots.
Normal completion copies all non-Val outputs in positional order; escaping
exceptions copy none. Result and the entire outgoing graph packet are validated
and copied before caller storage is written. Val formals never copy out.

Scope is exact mutable Array and Structure with String/Number/Boolean/Undefined
leaves. Cycles, other object classes, host subclasses and non-variable non-Val
sinks (including forwarded property/index references) fail closed. Named Val
forwarding of opaque property/index references is also outside this bounded
storage contract. Local packet limits are10,000 visited occurrences and depth64,
not claimed native limits. Shared DAG expansion consumes this occurrence budget.
Module state, other object serialization, NoContext and dual directives remain
required subsequent work. Same-side calls retain ordinary reference semantics.
This targets the captured Linux/amd64 managed file-infobase8.3.27.1508; it does not
resolve the documented alias/exception disagreement by inventing a file-mode rule.

`object_transfer_native.json` records the independently captured values, not
interpreter-generated expectations. Native and host now require the same109
values, and host computes them from the exact complete staged source. That source
is byte-identical to the audited mixed capture. Host preflight now permits exact
Boolean results as well as strings/integral numbers. Temporary observation-list
and error-stage metadata and shared-source execution inverse are removed; the
source-local failure sentinel still causes strict rejection without exposing raw
errors. Existing four-client adapter outputs and all security/size limits remain
unchanged. Current implementation-head native parity, independent audit and all
four OS checks remain required before ready/merge.


## Accepted object slice and later isolated measurement

The implementation passed strict109 on actual main
`0dbb93818f9cf18e48aa0e493e86557ddd272c58`, [run 39969439403](https://github.com/Atridis/yadinassi/actions/runs/39969439403),
with independent source/provenance/native/client/watchdog artifact audit.
Summary ZIP SHA256 `21d3da17472cfa329e383ec5430c229cb85b8ed184e0fd5ac03e200bf77d94d6`;
outputs ZIP SHA256 `b2d302e4a996cca812a4c1ef3361cda7408cbfbd4db59651778b6e2110143586`.
This supersedes the earlier pending-native status. A separate
[module-variable measurement](module-context-measurement.md) now temporarily
restores this exact accepted109 source for host preflight, without claiming
support or parity for the newly appended module-variable scenario.
