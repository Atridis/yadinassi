# Automatic trusted native 1C checks

The native workflow runs the six current regression scenarios on real 1C for
owner-authored pull requests from `Atridis/yadinassi` into `main`, including
Drafts, and owner pushes to `main`. It is separate from the unchanged four-platform
build matrix. No manual 1C launch or saved-output generation is needed for these
supported events. Tags, releases, forks, other authors/actors, arbitrary refs,
manual dispatch and privileged PR triggers are outside this route.

PR events are exactly `opened`, `synchronize` and `reopened`. A title/body edit or
Draft-to-ready transition does not rerun unchanged code. Retargeting an existing
PR into main requires a subsequent push (`synchronize`) or close/reopen to obtain
fresh checks for the new base. Until then, a missing native check is unavailable
evidence, not a pass.

## Identity and honest checks

Admission validates the exact repository and owner identities, event type, main
base/ref, PR author and head repository, original actor and rerunning actor.
Admission and the final verdict have no token permissions and perform no checkout.
Only an eligible native job receives `contents: read` and `packages: read`.
Excluded or malformed events fail admission without native execution. The final
verdict fails when admission or native execution fails, is skipped, is cancelled,
or has not completed successfully. A skipped native job is never a green native
result. A missing workflow run likewise provides no evidence.

Checkout uses the immutable event `github.sha`, without persisted credentials.
For a PR this is GitHub's synthetic merge commit, not its head. Its ordered parents
must match the event's base and head SHAs before registry access. Main pushes must
match the exact event commit. Existing runtime provenance independently verifies
checkout HEAD, tree and run/attempt identity. A rerun certifies its original
revision, not a later head or base; review/merge must compare current identities.
Per-PR/ref concurrency does not cancel an already running native cleanup.

These checks are not repository protection settings. No branch rule or required
check has been installed by this change. The workflow deliberately has no path
filters, so an otherwise eligible change cannot silently avoid its verdict.
There is no tag execution or release dependency in this route; existing releases
continue to depend on the four build jobs only.

## Fresh reference, not cached goldens

Every eligible execution creates a fresh disposable database in the same approved
digest-pinned image, validates the bounded role/user/protection readbacks, observes
the actual platform version and verifies the simple EPF. It then builds and runs
all six current scenarios through the existing launcher. No former database,
output artifact or cached reference can satisfy the current run.

The exact native bytes are transported privately with bounded nonce/hash checks.
The host runs a fresh interpreter process for each current source under UTC and
explicitly selects `linux-8.3.27.1508` / `typed-map-order-v1`. Five current outputs
are byte-exact; the source-bound Map contract may accept only the eight reviewed
payload records without pair order, retaining types, bindings and real roundtrip
checks. All other results remain strict. Raw differences and semantic acceptance
remain separate. See [the full comparison contract](native-1c-full-regression.md).

The registry image can use infrastructure caching, but native outputs are never
cached as an oracle. Historical Windows `8.3.27.2342` outputs remain unchanged for
offline/default-target and frozen-build regression checks in
`tests/fixtures/native_windows`. The launcher destination `integrational_tests/output`
is disposable and ignored except for its tracked `.gitkeep`. They are not relabeled
as Linux results; removing them requires a separate dependent-test migration.

## Unchanged isolation and artifact scope

The image digest, disposable administrative role, legacy 23 read-only inputs
(24 with the explicit client checkpoint below),
resource/time bounds, readonly root and tmpfs data/logs remain unchanged. No
container network, exposed ports, token, Docker socket or writable host mount is
added. Authentication uses the existing short-lived job token on the host, with
private registry configuration deleted before native execution. Native-job actions
are pinned to the verified official v7 commits; no new account, credential,
package grant or repository setting is introduced.

The same seven-day public artifacts are retained: the finite summary and exactly
six native `.out` files plus finite `provenance.json`. These test outputs include
intentional error messages. Raw service logs, `.err`, database, XML/EPF files,
image contents and credentials are excluded. Publication requires the existing
source/evidence/cleanup and exact-file export gates. Actual output bytes are never
normalized or replaced to obtain a pass.

## Package privacy and trusted code

The owner explicitly accepted the existing public-repository package access model
for this training image. GitHub documents that granting a public repository access
to a private package can also allow access from forks. A fork's read-only token
can request package read; maintainer approval controls whether a run starts, not
package confidentiality after code runs. The effective repository approval policy
is not established by this workflow.

Fork/actor guards exclude forks from **our native route**, not from every possible
workflow a contributor might propose. Editable YAML, host orchestration and
interpreter code must be trusted/reviewed: container isolation does not sandbox
that host code or guarantee secrecy of the image. No claim of an actual leak is
made. No package visibility/access, Actions approval or branch-protection setting
was changed. Never replace this route with `pull_request_target` or a privileged
workflow that executes an untrusted head.

References:
- [Private package access from workflows](https://docs.github.com/en/packages/managing-github-packages-using-github-actions-workflows/publishing-and-installing-a-package-with-github-actions#default-permissions-and-access-settings-for-packages-modified-through-workflows)
- [Fork token permissions](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax#changing-the-permissions-in-a-forked-repository)
- [PR merge-ref semantics](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
- [Rerun identity and privileges](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/re-run-workflows-and-jobs)

### Opt-in managed-form client checkpoint

`--client-probe` requires `--full-suite`. It adds exactly one trusted input,
`scripts/native_1c_bootstrap/client_probe.bsl`, to the existing 23-file full-suite
manifest. Without the flag, the legacy manifest and report schema remain
unchanged. `--client-watchdog-check` additionally requires both `--client-probe`
and `--full-suite`. The approved PR/main CI command explicitly enables both; when enabled,
a missing, failed or incomplete client checkpoint cannot yield suite success or
export the six-output artifact.

`--client-dates-parity` is a separate opt-in requiring both `--full-suite`
and `--client-probe`; it also works with `--client-watchdog-check`. The isolated
CI job opts in explicitly. It reuses the already staged `dates.bsl`
and client-probe template, so the trusted manifest remains exactly 24 files.
The host hashes the generated client dates module from those staged inputs.
The private client dates result must match the server dates result byte-for-byte;
missing or invalid parity evidence cannot pass an opted-in run. Its finite
report records validation metadata only; raw client dates output stays private.
The public artifact still contains only the same six scenario outputs and
provenance. A fresh successful native run is required before accepting this
checkpoint; local synthetic fixtures do not establish native parity.

The adapter is pinned to the complete original dates source and template. It
preserves both helpers, all expressions, exception branches and execution order,
and changes only five verified `Сообщить` identifiers to an explicitly scoped
string capture. It performs no additional `Строка` conversion. All 100 messages
(98 observations plus two checkpoints), including multiline values, are serialized
with the existing UTF-8/LF rules and compared in full against the fresh server
`dates.out`, without prefix filtering or map-order relaxation. The inverse adapter
must recover the original normalized source exactly. This proves expression/result
parity with explicit string capture, not unchanged client `Сообщить` UI behavior;
expected error observations do not establish that those APIs succeeded.
No runtime budget, mount, network policy, capability or bootstrap right is
expanded by this option.

`--client-values-parity` independently opts into the complete `values.bsl`
checkpoint and requires `--full-suite` plus `--client-probe`. The isolated CI
command enables it alongside dates and the watchdog: the unchanged six server
scenarios run first, followed by the fixed client probe, dates parity, values
parity and the deliberate watchdog checkpoint. The same 24 trusted inputs,
six public server outputs and provenance are retained. Raw client values
markers stay private; only finite validation metadata enters the report.

The values adapter pins the original source and template, preserves all 33
helpers and the entire top-level body, and replaces only the 16 verified
`Сообщить` call identifiers with bounded string capture. It adds no `Строка`
conversion and checks inverse source reconstruction. All 261 messages (40 Null,
62 XML, 132 types, 23 types-extra observations and four completion markers)
are compared byte-for-byte with this run's fresh server `values.out`, including
order, multiline content and trailing bytes. No historical output hash is used
as the parity oracle. Context differences in Null, XML or type-qualifier APIs
must fail the checkpoint rather than be normalized or accepted as map-order
exceptions. Existing expected-error observations still do not establish API
success. The same nonce, module/EPF round-trip, on-open client invocation,
process/session-bus census and bounded watchdog checks apply; neither summary
nor full-report limits are increased. Local adapter and synthetic-marker tests
are not a real-1C parity result.

This is a logical execution-context test in the explicitly launched file-mode
thick client, not proof of a separate physical server process. File mode can
also support other client types; no universal thick-client claim is made.

After the unchanged six **server-object-module context** scenarios succeed, the helper
builds a distinct private `ClientProbe.epf`. It copies the reviewed Launcher XML
and comment-only object module, replacing only the private managed-form module.
The original Launcher, TestModule and six BSL scenarios are not edited. All probe
helpers and `ПриОткрытии` are `&НаКлиенте`; no server invocation exists. The
`#Если Клиент` branch is only a compatibility assertion: in file-mode thick
client both client/server preprocessor symbols can be defined. It is not a
discriminating context witness. The route evidence is the verified managed-form
OnOpen handler and its directly called `&НаКлиенте` helpers, with no server
transition. The OnOpen handler itself computes arithmetic `42`, string
`client-probe`, and array count/sum `3`/`6`. A literal context label without the
verified source, form wiring and calculations is not accepted as client proof.

Designer builds the EPF and re-dumps it through
`/DumpExternalDataProcessorOrReportToFiles <root XML> <EPF>`, the platform's
[documented external-processor dump route](https://edt.1c.ru/dev/edt/2025.2/apidocs/com/_1c/g5/v8/dt/platform/services/core/runtimes/execution/impl/IRuntimeExecutionCommandOptions.html).
The verifier requires the same managed DefaultForm/OnOpen wiring, no executable
object-module body, and byte-exact form-module round-trip after only BOM/newline
normalization. Source, generated module and re-dumped module hashes appear in
the bounded report.

Each invocation uses a fresh nonce and previously absent private request,
entered and completed paths. Strict bounded JSON validation rejects duplicate
or unknown keys, wrong nonce/context/phase/types/values, partial files, links,
special files, oversized evidence and reversed marker modification order.
Completion requires both records, expected values, clean process exit and
native-process quiescence. A handled error record is not completion.
The external 120-second process-group watchdog remains authoritative before
OnOpen, during calculations and after a completed marker. No marker overrides
a timeout or nonzero exit. A timeout is a timeout, **not proof of a modal dialog**.
No dialog clicks, UI automation or added security rights are used. The fixed
`stall` checkpoint mode deliberately loops after entered, without opening any
modal window. `--client-watchdog-check` builds a separate private EPF invocation
after the positive proof. It accepts only the expected 120-second timeout, a
valid entered marker, no completed file (including no partial/error file), and
verified quiescence. Missing entry, early exit, nonzero exit, a completed record
or failed cleanup fails this negative assertion. This adds 120 seconds to the
normal checkpoint but leaves the existing 2400-second outer budget unchanged.

Before the first native invocation, after display startup, client opt-in starts
one explicitly owned `/usr/bin/dbus-daemon --session --nofork` child using the
pinned image's existing session policy. Its nonce-private Unix socket lives in
a new mode-0700 tmpfs directory; the exact address is exported without any
host/system bus, TCP listener or autolaunch fallback. Bounded readiness checks
verify UID, parent, executable, kernel start time, printed address and socket.
Only then does the harness record the permitted process identities in its
isolated PID namespace. The owned bus must remain live through both probes;
service activation does not exempt any additional process from the census. Only its own
subsequent runner identity is admitted. PID plus kernel start time prevents
PID reuse from disguising a new process; every process is counted, even
non-dumpable or different-executable descendants. Missing/unreadable census
evidence fails closed. A clean leader exit with lingering group members fails
after a bounded grace period rather than becoming success through cleanup.
Only each launched native group is killed; escaped survivors cause failure and
are left to the existing container teardown, never a broad same-user kill.
At harness exit, the explicitly owned bus is pinned with a pidfd, identity
checked, then stopped with TERM/KILL under a four-second total bound and reaped.
Missing pidfd support, bus death/replacement or cleanup failure prevents success;
there is no numeric-PID or process-name cleanup fallback. After bus teardown,
a final census against the original baseline rejects late service activation
before any output export.

The same fresh database and verified `NativeSmoke` warning-off bootstrap are
used. The five role rights, pinned image, non-root execution, read-only root,
network isolation, tmpfs and resource limits are unchanged. The new bus lifecycle
uses only the already isolated container and its private tmpfs. Public
artifacts remain the six `.out` files plus provenance; the existing finite
report adds only fixed status/boolean/hash fields and bounded process counts/classes. Probe JSON, EPF, database,
logs and screenshots are never exported. The existing 32 KiB report, 8 KiB
stage report, 3 MiB transport, 1 MiB per output and 2 MiB aggregate caps remain.

This checkpoint proves only this small client execution route. It does not
relabel the six scenarios as native client parity, establish Windows behavior,
or validate any actual modal interaction. Local synthetic tests do not replace
a successful native checkpoint; native positive and deliberate-stall results
must be reviewed before claiming the new route is verified.

The durable client evidence is in the existing `native-1c-full-summary` artifact
(`native-smoke/report.json`), bound to the invocation nonce, repository commit
and tree, all 24 trusted input hashes and the measured `SystemInfo.AppVersion`.
The separate `native-1c-six-scenario-outputs` artifact still has exactly seven
members (six `.out` plus `provenance.json`); that legacy provenance describes
only the six server scenarios and makes no client execution claim.

Failure diagnostics expose only fixed process-check stage/reason and bounded
counts/classes. They never expose process identifiers, start times, executable
paths, command lines or logs, and cannot override a failed process gate.

`--client-collections-parity` independently opts into the entire `collections.bsl`
scenario and requires `--full-suite` plus `--client-probe`. CI enables it after
values parity and before the controlled watchdog checkpoint. Its hash-pinned
adapter preserves all 112 helpers, the module-global `Выход`, 16 region directives,
and the complete body. Only 15 verified `Сообщить` identifiers are replaced by
bounded string capture; existing conversions and helper-local dynamic execution
remain intact. Four source-pinned helper-local declarations preserve `Объект`
and `Элементы` as locals, preventing accidental binding to the managed form's
Object attribute and Items collection. Identifiers and dynamic expression text
are not renamed. Inverse reconstruction removes only these exact additions and
must recover the original source exactly.

All 797 messages are compared as complete UTF-8/LF bytes with this run's fresh
server `collections.out`. API availability, localized errors, message order and
Map order differences fail this client/server checkpoint; the eight existing
interpreter/server Map exceptions do not apply. No historical output hash is a
parity oracle. Raw client messages remain private. The same 24 staged inputs,
six public server outputs and provenance, isolation and nonce/round-trip/process
proofs remain required. A strict collections mismatch can include only finite
metadata in the existing report: differing-message count, first ordinal, earliest
16 differing ordinals, and hashes/sizes of the first differing serialized message.
The private server message array must reproduce the same fresh server output
before ordinal metadata is emitted. No raw client messages are exported, no new
artifact is added, and mismatch diagnostics never enable success or exceptions.

Schema 2 exists only on the compact stage wire transport;
legacy schema 1 remains supported when collections is not selected. Compaction
losslessly groups the three source/module/round-trip hashes and five proof
booleans; host reports restore the existing named schema-1 evidence fields.
Malformed, mixed or ambiguous wire records fail closed. The 8,192-byte stage and 32,768-byte full-report caps
are unchanged. Offline tests are not evidence of execution or parity on real 1C.

### Full numbers client execution with narrow native conversion calibration

`--client-numbers-parity` independently adds the complete unchanged `numbers.bsl`
scenario after collections and before the negative watchdog. It requires the
full suite and fixed client probe. The adapter pins the source SHA-256
`72837cfab6a37506e22408c8b7e620fe8582e9c63214d09e85bb087b1c2a7d86`,
template, 659 source lines, 19 helper declarations/endings, body boundary and
four message-call sites. Inverse reconstruction restores every source byte;
helpers and dynamic evaluation retain their local scopes. No server trampoline,
interpreter-produced expected text, historical fixture or omitted case is used.

Three call sites already supply strings and use string-only bounded capture.
The remaining site is source line 307, `Сообщить(1234.5)`, yielding zero-based
message ordinal 30. Only that site calls a separate typed capture routine: it
requires `Тип("Число")`, exactly `1234.5`, and exactly 30 previously captured
messages, then applies the platform's native `Строка`. Other numbers, Boolean,
Undefined, Null and strings are rejected there; all non-strings are rejected by
the ordinary capture routine. This is intentionally not generic coercion.

The native run must compare all 350 serialized client messages byte-for-byte
against the fresh same-run server `numbers.out`. It also reads the unchanged
server launcher's private `numbers-case/result.json`, verifies that its full
message array reproduces those exact server bytes, and checks the pinned
`present.string`, `present.concat`, `present.direct.next` and following marker
positions on both sides. The string/concatenation payloads must equal the raw
number record, without any hardcoded numeric text. Only after these gates does
`conversion_verified` become true; host validation requires that proof, the
pinned source/generated-module identities and exact fresh server output hash,
size and count. Failure/late process-census invalidation clears the proof.

This establishes full numbers client execution and native-conversion parity
against actual server `Сообщить`. It does **not** measure the managed client's
UI `Сообщить` rendering or establish general number-formatting equivalence.
Offline tests check structure, typing and orchestration only; a new native run
is required before claiming native parity.

Numbers selects stage-wire schema 3, which retains the existing ordered
hash/proof arrays and losslessly packs process-diagnostic field names into a
fixed array. Host and stage decoders restore every named schema-1 evidence
field, reject malformed/mixed versions, and preserve schema-1/2 behavior for
existing modes. No evidence is discarded and the 8,192-byte stage / 32,768-byte
full-report caps are unchanged. The six-record synthetic success report fits
under the stage cap; tests also cover numbers without the other parity modes.
The 24 staged inputs, six server outputs plus provenance, fixed image/network/
role isolation, client witness, fresh nonce, roundtrip, 120-second watchdog,
process census and cleanup gates remain unchanged. Client output stays private.
