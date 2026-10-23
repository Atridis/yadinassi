# Native client Async/Await measurement (opt-in)

This is a measurement harness, not interpreter Async/Await support or a parity claim. The existing server postCreate contract, six server scenarios, simple client witness, and standard CI parity/watchdog invocation are unchanged.

A separately approved invocation can use:

```sh
python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --client-probe \
  --client-async-measurement --output native-smoke/report.json \
  --export-native-outputs --native-target linux-8.3.27.1508 \
  --comparison-mode typed-map-order-v1
```

The measurement flag cannot be combined with optional client parity or watchdog flags. This does not replace standard CI coverage. The owner-only manual fallback requires an explicit true measurement flag and a reviewed commit SHA matching the dispatched same-repository branch revision. False/missing flags, forks, tags, and mismatched revisions are rejected. Running the command requires the existing approved native image and execution environment.


## Reviewed push opt-in

The exact same-repository branch `codex/native-client-async-reviewed` is a
separate launch control, not a development branch. After reviewing a candidate
commit and verifying its standard CI, fast-forward this branch to that exact
commit, checking the expected previous head before updating it. Do not push
unreviewed work to this branch. A branch name alone does not prove review; the
intentional promotion is the opt-in decision. When bootstrapping, create the
branch at the previous commit, then promote it to the reviewed candidate and
verify a `push` run for the candidate SHA, rather than assuming that creation
alone launched it.

Only that exact push ref selects the bounded async command. Existing PR and
`main` routes keep the standard comparison, and `workflow_dispatch` with its
explicit flag and matching `reviewed_sha` remains available. Admission preserves
the owner/repository numeric identity checks and rejects forced or deleted
reviewed-branch pushes, mismatched event/checkout/workflow revisions, tags and
other branch contexts. An async verdict cannot satisfy the standard required
verdict name; skipped, failed or cancelled execution is not successful evidence.

No new credentials or token permissions are introduced: execution retains
`contents: read` and `packages: read`, the approved image digest, isolated
container and fixed public artifact inventory. These checks do not prevent
repository editors from modifying workflows and do not narrow the existing
public-repository package grant. The opt-in route does not create a new image
confidentiality boundary.

## Fixed language-only observations

Eight freshly built managed client forms measure:

1. Async function return type and explicit joining.
2. Await of a settled Promise and actual caller/callee event order.
3. Multiple retained branches and explicit completion of every branch.
4. Await of scalar values, preserving results or caught errors.
5. Nested Promise return behavior, preserving actual type and result.
6. Val/default-parameter behavior and unmarked scalar observations.
7. Error timing at call versus first/repeated Await and propagation.
8. English/mixed-case core grammar and a handled Async procedure.

No UI, network, or file-async API families are measured. Completion transport uses synchronous private file I/O only. Compiler-negative cases, task-local context, Decimal behavior, and import diagnostics are deferred.

The fixed per-case event inventory, conditional branches, and partial-order edges are independently specified by the protocol tests. An accepted trace contains every required event exactly once, in its actual native order; it is not rewritten into an expected schedule. Values retain finite type tags and actual bounded payloads. Unsupported types or out-of-bound observations produce an inconclusive result, not a normalized success. Expected error paths preserve selected exact descriptors privately; public evidence contains finite field classifications and SHA-256, never free-form error text. Recursive error/source parity is not claimed. Unexpected root or sibling failures fail closed with no accepted trace; they produce finite failure evidence and only the available private platform logs, not a dedicated caught-error sidecar.

## Completion and evidence

Only the Async root writes completed and exits. It joins all retained Promises, including cleanup paths; no sleep proves completion. Each launch uses a fresh directory, exact canonical request, invocation nonce, client witness, exact generated-module and native roundtrip hashes, clean process/session checks, and strict complete markers. Early exit, partial/noisy markers, wrong witness/nonce, stale files, and unexpected processes fail closed.

Private continuity evidence records fixed-path metadata identities and byte hashes. Schema 4 carries its SHA-256 from the stage to the final emitter; final export verifies the digest and every fixed entry again. Replacing evidence and rebasing the private manifest cannot satisfy the retained report digest. A failed/inconclusive/unreached measurement carries no continuity digest.

The old process timeout remains exactly 120 seconds. Async-only operations use at most 120 seconds each, bounded further by the remaining shared deadline; the deadline is conservatively anchored to shell start with finalization reserve. Deadline exhaustion fails without accepting partial traces.

## Public boundary

The staged input inventory remains 24 paths. The stage wire cap remains 8192 bytes; summary and provenance caps remain 32768 bytes each. Public output classes remain six existing `.out` files, finite provenance, and finite report. No raw logs, marker files, continuity manifest, database, EPF, or screenshots are exported. Reports explicitly mark measurement purpose and `client_async_parity_claimed: false`.

Offline tests exercise synthetic observations and transport failures. They do not establish native compilation, scheduling, or platform API behavior. Native execution and independent artifact audit remain a separate gate.

## Failure localization, not semantic evidence

Schema 4 also carries `failure_diagnostics`: normally null, or a four-integer tuple
`[host_stage, entered_observation, completed_observation, native_log_category]`.
The finite host stages are preparation, build, roundtrip, enterprise, marker
validation, and continuity. Marker states are not_checked, observed_absent,
observed_invalid, or observed_valid. These are bounded, stable observations after
the process group has stopped, not assertions that files remain unchanged until
publication. They do not replace successful completion or continuity proofs.

The entry wrapper emits only a finite startup-failure label into the existing
private platform log: request, witness, initialize, entered, or root. Request
localization additionally distinguishes open, object, key, value, end, fields,
nonce, and paths operations using fixed request-prefixed labels. These labels
identify the operation group being attempted, not the statement-level cause or
Async language behavior. Request validation remains strict; no fallback parser
or free-form error information is added. The four request-key operations have
literal labels assigned immediately before the read guard, token guard,
current-value assignment, and property check. Each distinguishes the first
iteration from any later iteration. These eight labels append wire categories
31–38; existing categories 0–30 retain their meaning, including the helper-call
category 26 and retired source-classifier categories 27–30. Request-end labels
append categories 39–43 for the end-token call group, Read guard, token assertion,
trailing Read/rejection, and Close respectively. Existing categories 0–38 retain
their meaning. The end-token expression is now assigned to an explicitly local
`AsyncRequestEndToken` in `AsyncReadRequest`, before the original Read guard and
token comparison. These end operations and their labels stay in that one
routine, without the former `AsyncExpectRequestEnd` helper. The end-token
expression now uses `ТипЗначенияJSON.КонецОбъекта`; token evaluation before
reading, validation order, and all guards are preserved. Category 39 retains the wire label
`request_end_call` for compatibility; its current operation is the token
evaluation/local assignment. No new category or schema is added.

The key helper remains unchanged. No ErrorInfo calibration,
source-line matching, or cause-chain classifier is used. A label identifies the
operation being attempted, not whether an API access, guard, or Raise failed,
and it is never successful Async evidence. Other native log categories
are diagnostic classifications, not proof of a particular cause. No raw log
text, error description, new sidecar, or new artifact class is exported.

The request reader declares `AsyncRequestKey` locally and uses it in place of
implicit `Key`; `Reader.CurrentValue`, validation order, and all eight measured
cases are unchanged. This bounded scope correction avoids depending on an
undeclared name in the form context. The observed first current-value assignment
failure does not distinguish getter failure from assignment failure or establish
a `Key` collision. Subsequent native measurements reached the request-end
operation group without successful entry/completion markers or Async evidence.
In [run 39949728087](https://github.com/Atridis/yadinassi/actions/runs/39949728087),
the retained label was category 39. At that revision the end guards were in a
nested helper; propagation of a changed scalar stage through that helper's
escaping exception had not been measured independently on native 1C. Therefore
category 39 did not prove that the helper was never entered, that Read was never
attempted, or that the enum member was invalid. Inlining removes that additional
diagnostic transport boundary. The subsequent inline
[run 39953760732](https://github.com/Atridis/yadinassi/actions/runs/39953760732)
also retained category 39, now immediately before the enum evaluation and local
assignment in `AsyncReadRequest`. This localizes the remaining failure to that
operation group, not to a nested helper; it still does not distinguish enum
lookup from local assignment or establish a general English-alias defect.

The next bounded experiment changes only that expression from
`JSONValueType.ObjectEnd` to `ТипЗначенияJSON.КонецОбъекта`, plus the corresponding
fixture/host identity pins. The Russian spelling appears in the vendor's
[JSON reader example](https://wonderland.v8.1c.ru/blog/sredstva-raboty-s-json/)
([original code image](https://v8.1c.ru/o7/201410json/1.png)). This is a
target-specific compatibility experiment, not a claim that the English alias is
generally invalid or that the change has already succeeded on native 1C. No
request grammar, measured case, stage, schema, cap, artifact, or CI route changes.

The source-bound offline enum doubles expose the exercised English members and
that one Russian member separately, mapping it to the unchanged internal
`ObjectEnd` token. Rejecting unused spellings in those exact-source doubles does
not model native case sensitivity or prove the full native alias inventory.
Controlled getter/assignment failures, all 120 key orders for each of eight
modules, strict-negative tests, and exact-inverse source/pin checks are not
native proof of the underlying cause; another native measurement is still
required.

For a failed case, semantic proof stays zero, trace/value/error observations stay
empty, and the measurement's continuity stays null. Valid diagnostic markers never turn a timed
out or otherwise failed process into accepted measurements. When entry is not
observed and logs are inconclusive, compilation, startup, and an unobserved
client failure remain unresolved alternatives.


## Marker validator discriminator (inner report version 2)

[Run 39956806191](https://github.com/Atridis/yadinassi/actions/runs/39956806191)
reached accepted per-case traces for cases 0–5. Case 6 failed with
`invalid_result` and diagnostic `[4,3,2,3]`: marker validation stage, observed
valid entered marker, observed invalid completed marker, and no specific native
log category. Case 7 was not reached. The aggregate was not accepted and its
continuity digest was null. Those public fields do not identify an ErrorInfo
field, an error phase, a missing event, or a violated causal edge. In particular,
they do not establish different rejected-Promise semantics.

A new failure-only `marker_validation_failure` field distinguishes those
alternatives without changing any accepted marker predicate or BSL source.
The inner `client_async.version` is explicitly 2; outer schema 4, request/marker
schema 1, generated modules, the 24 staged paths and all artifact/size caps stay
unchanged. Version 1 inner records are not accepted by the version 2 reader.
`failure_diagnostics` retains exactly its existing meaning, including its fourth
native-log-category member.

The new field is normally null. A non-null value is exactly
`[marker_phase, validator_site, descriptor_ordinal, field_locator]`, four strict
integers. Marker phase is 0 for entered or 1 for completed. Descriptor ordinal
is 0–2 only at descriptor/reference sites, otherwise sentinel 3. The locator is
site-specific, never a raw string or native scalar value; sentinel 31 means not
applicable. Descriptor field ordinals are schema 0, phase 1, description 2,
code 3, additional 4, category 5, cause 6, module 7, line 8, and source 9.

| Site | Rejection | Locator |
| --- | --- | --- |
| 1 | JSON UTF-8 decoding | 31 |
| 2 | JSON depth | 31 |
| 3 | Duplicate JSON key | 31 |
| 4 | JSON integer token width | 31 |
| 5 | JSON float token | 31 |
| 6 | JSON non-finite constant | 31 |
| 7 | JSON syntax | 31 |
| 8 | Marker envelope shape/keys | 31 |
| 9 | Marker schema | 31 |
| 10 | Completion status/failure code | 31 |
| 11 | Failed/inconclusive completion shape | 31 |
| 12 | Nonzero failure code on successful completion | 31 |
| 13 | Error-list shape/length | 31 |
| 14 | Descriptor shape/keys | 31 |
| 15 | Descriptor schema | 0 |
| 16 | Descriptor phase type/range | 1 |
| 17 | Descriptor pair shape | Descriptor field 2–9 |
| 18 | Descriptor field tag | Descriptor field 2–9 |
| 19 | Descriptor absent/Undefined payload | Descriptor field 2–9 |
| 20 | Descriptor string payload type | Descriptor field 2–9 |
| 21 | Descriptor string character/UTF-8 limit | Descriptor field 2–9 |
| 22 | Descriptor integer payload | Descriptor field 2–9 |
| 23 | Descriptor Boolean payload | Descriptor field 2–9 |
| 24 | Descriptor native-type payload | Descriptor field 2–9 |
| 25 | Descriptor Unicode/canonical encoding | Descriptor field 2–9, or 31 |
| 26 | Canonical descriptor byte budget | 31 |
| 27 | Observation list shape/length | 31 |
| 28 | Event type/range | 31, never the invalid payload |
| 29 | Duplicate event | Known event ID 0–28 |
| 30 | Root trace boundaries | 31 |
| 31 | Value-pair shape | Fixed case slot |
| 32 | Value tag | Fixed case slot |
| 33 | Value payload | Fixed case slot |
| 34 | Referenced error phase disagrees with fixed slot phase | Fixed case slot |
| 35 | Error reference/ordinal | Fixed case slot |
| 36 | Error-reference bijection | 31 |
| 37 | Not-executed slot disagreement | Fixed case slot |
| 38 | Missing required event | First missing known event ID |
| 39 | Excess event | First excess known event ID |
| 40 | Causal order | First violated edge ordinal in the frozen case DAG |
| 41 | Required handled-error observation | Slot 2, case 7 only |
| 42 | Unclassified rejection | 31 |

The discriminator runs only after the original strict parser/validator rejects.
It cannot turn failure into success or rewrite observations. Its deliberately
bounded duplicate checks are diagnostic, not an alternate acceptance path.
The field is permitted only for `failed` / `invalid_result` at marker stage,
with the selected marker observed invalid; a completed-marker hint additionally
requires observed valid entry. Both validators enforce exact per-site locator
and descriptor ranges. Accepted traces and error descriptors are never retained
on the failing case: its proof stays zero and its trace/value/error lists empty.

Capture requires confirmed process stop and the original securely retained
request, entered and completed snapshots. It checks freshness and marker order,
then checks every snapshot again after classification. Missing original pins,
stale timestamps, changed files (including same-byte inode replacement), or
known nonce/case/phase/witness disagreement yield null. For malformed JSON,
only the finite parser rejection is reported from the pinned private path; no
identity or semantic observation is inferred from unparseable bytes. The final
emitter preserves this historical capture and does not reread or rebase it.
Unknown is a bounded rejection site, never successful evidence.

Offline tests pin all original marker-acceptance function bytes and all BSL
fixture identities, compare classifier verdicts with both strict validators,
and exercise parser/descriptor/reference/inventory/DAG failures and late
replacement. Actual serializer checks retain the 8192-byte stage limit and
32768-byte summary/provenance limits. A fresh native run and independent audit
are still required to learn which marker predicate rejected case 6.

### Error-descriptor JSON transport correction

Native run [39961019232](https://github.com/Atridis/yadinassi/actions/runs/39961019232)
reached the first error-bearing case, case 6, and rejected its completed marker
with `[1,7,3,31]`: completed phase, JSON-syntax rejection, no descriptor or field
locator. Cases 0–5 were only provisional observations; this is not an accepted
complete measurement. The discriminator does not identify a particular byte or
prove which serializer input caused the malformed marker.

The automatic global `WriteJSON`/`ЗаписатьJSON` API has a documented mapping from
`Undefined`/`Неопределено` to JSON `null`. `Null` is not in its supported automatic
input types; unsupported types cause an exception. See the vendor's
[JSON overview](https://wonderland.v8.1c.ru/blog/sredstva-raboty-s-json/) and
[Developer Guide](https://1c-dn.com/download-trial/files/guides/developer_guide.pdf),
§16.2.2.1 (PDF page 1093) and §16.2.2.2 (PDF page 1095).
The separate XDTO serialization described in §16.2.3 (PDF page 1106) supports
`Null`, but that is not the global automatic serializer used by this fixture.

The transport correction changes exactly twelve payload sentinels in
`АсинхПоле` and the guarded initial error fields: eleven `[0, Null]` and one
`[1, Null]` become the same tagged pairs with `Неопределено` as the BSL payload.
The JSON payload remains `null`; tag 0 still means unavailable and tag 1 still
means an observed Undefined field. No tag, descriptor schema, Python validator,
canonical hash rule, accepted evidence, cap, timeout, process rule, artifact,
or permission is changed. All eight semantic case bodies are byte-identical,
including case 3's `Await Null`, and the semantic Null value mapping remains
`[2,0]`. Only the template/module/aggregate source identity pins change with the
production source.

Offline tests execute exact generated capture and completion routines against a
bounded, source-spelling JSON writer double. The double accepts Undefined as
JSON `null` and rejects BSL Null, including nested inputs; the inverse previous
fixture therefore fails under the same model. Controlled unavailable getters
and Undefined-valued fields preserve their distinct tags and fingerprints.
Quotes, backslashes, CR, LF, tabs, all U+0000–U+001F controls, and Unicode text
round-trip through a strict serializer without manual escaping. These are
source-bound model tests, not native API implementation or native Async proof.
Exact inverse tests restore both reviewed production files after undoing only
the twelve sentinels and identity pins. Actual production Python serializers
are still used for the unchanged stage/summary/provenance budget proof.

This is a documented API correction and a hypothesis for the case-6 failure,
not a proven native repair. A fresh complete native measurement and independent
audit are still required before any Async parity conclusion or readiness claim.
