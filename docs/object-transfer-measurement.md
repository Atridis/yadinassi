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
is SHA256 `6a218ea202eea46f7ccb41534db3d3228d49435d0bb44598b30eefd891891aae`.
The integrated adapter keeps all operations/calls in place. It only changes the
client entry to return a local record array and its recording sink. Standalone
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
