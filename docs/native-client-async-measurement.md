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
