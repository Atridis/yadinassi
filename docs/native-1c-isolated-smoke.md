# Isolated native 1C bootstrap and simple EPF smoke

This is a bounded validation of one approved Linux training image, not the full
native regression suite. The first capability-only run established Python 3.10.12,
non-root execution, dynamic-library resolution, authenticated display startup,
empty database creation and hierarchical configuration export (schema 2.20).
It did not establish the actual application version or user/bootstrap behavior.
The first stage-two native run confirmed full module import, database update and
byte-identical re-export, then failed in anonymous bootstrap with a nonzero process
result. At that stage, persisted security state and actual version were unverified.
The subsequent diagnostic-only run identified our whole-property Boolean guard
as the failure before protection assignment or user Write. The descriptor-gated
retry then observed the actual descriptor type and inner Boolean, but failed on
an unsupported `Количество` call during bootstrap. After replacing the role
Count check with fail-closed enumeration, [the next native run](https://github.com/Atridis/yadinassi/actions/runs/39524919916)
failed with a runtime-error classification and matching session error marker.
That report did not retain a source location or method identifier. The following
[context diagnostic run](https://github.com/Atridis/yadinassi/actions/runs/39526355692)
retained `Записать` and `SessionModule` line 80, the actual user `Write()` call.
The descriptor checks and reject-first-role enumeration therefore reached Write.
The subsequent finite cause projection retained the requirement that at least one
user have administrative rights, consistent with the official first-user tutorial.

The bootstrap adds one explicitly named disposable administrative role,
`NativeSmokeBootstrapAdministrator`, to the fresh native empty configuration and
assigns exactly that role to the one bootstrap user. It is not a FullAccess role.
The five explicit rights are `Administration`, its documented prerequisite
`DataAdministration`, `ThickClient`, `MainWindowModeNormal`, and
`InteractiveOpenExtDataProcessors`. These are a documentation-based bounded set
for this workflow, not a runtime-proven mathematically minimal set. All three
role-default flags are false; no default role, other right or additional object
grant is permitted. The [role-bearing native run](https://github.com/Atridis/yadinassi/actions/runs/39559544886)
passed on commit `ab8c3444a84eb503fd59ce2084732d90aa737989`: exact role/module
redumps, user Write, persisted/fresh role and protection checks, named Designer,
measured `SystemInfo.AppVersion` `8.3.27.1508`, launcher and simple EPF. All 16
trusted input hashes matched. Offline mocks alone would not establish these facts.

The separately gated [six-scenario full mode](native-1c-full-regression.md)
reuses these prerequisites but keeps actual output payloads private and compares
them outside the container under UTC. Bootstrap-only success is not full-suite
success.

## Invocation and unchanged trust boundary

The temporary workflow `.github/workflows/native-1c-isolated-smoke.yml` runs only
on the exact `codex/native-1c-isolated-smoke` branch, in `Atridis/yadinassi`, pushed
and retried by `Atridis`. No PR, fork, main-branch, dispatch, tag or arbitrary-input
trigger is added. Its fixed relevant source-path filters now include the separate
full-suite helpers, six scenarios, launcher and interpreter. Remove this temporary
route after validation. A matching source push triggers execution and must remain
within the approved scope. The workflow selects the full mode documented
[separately](native-1c-full-regression.md).

The original bootstrap-only mode remains available with both explicit flags:

```
python3 scripts/native_1c_smoke.py --execute-approved-image --bootstrap-simple-epf --output native-smoke/report.json
```

Omitting both `--bootstrap-simple-epf` and `--full-suite` retains capability-only
mode. All modes use the
same fixed image, without a caller-supplied tag or executable:

```
ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728
```

The job package token is used only by the host for registry login/pull via stdin.
It is removed from the environment and its isolated authentication directory is
deleted before image inspection/execution. Checkout credentials are not persisted.
Neither a token nor the Docker socket is passed into the container.

Execution remains `linux/amd64`, numeric UID/GID `1000:1000`, no network, ports,
host PID/IPC, host-writable mounts, inherited environment or implicit image
volumes. The image entrypoint and healthcheck are disabled. The root filesystem
is read-only; `/tmp` is a 1 GiB noexec/nosuid/nodev tmpfs, shared memory is private
and limited to 128 MiB. Limits remain 2 GiB memory, 2 CPUs, 256 PIDs and 64 MiB
per file, with all capabilities dropped and no-new-privileges enabled.

Bootstrap-only stage two replaces the single probe-file mount with one read-only staged-inputs
directory. Its exact 16-file allowlist contains only the shell probe, four stage
Python helpers, two internal BSL modules, one fixed smoke scenario, and the existing
Python launcher plus its seven template files. Files and directories are copied
with explicit 0644/0755 modes so the non-root container can read them. Symlinks,
special files, extra files/directories and oversized sources are rejected. No
repository tree, `.git`, credentials, existing outputs or original test scenarios
are mounted. Host-computed source SHA-256 values accompany the validated report.

No packages are installed in the image. The authenticated `Xtigervnc` uses a fresh
Xauthority cookie, `-rfbport -1`, no RFB Unix socket and `-nolisten tcp`; X
and VNC authentication are not disabled. Capability calls retain 120-second
bounds plus a kill grace. Stage-two processes have 120-second bounds and process
group termination; the entire stage-two container is limited to 900 seconds
(capability-only mode remains 480 seconds). The full-mode container/workflow
ceilings are documented separately. Cleanup failure is never reported as success.

## Stage-two gates

All database files, native XML, logs, generated EPFs, request files and markers
remain in tmpfs. There is one fresh database and no concurrent 1C sessions.

1. Create an empty file database and export its native hierarchical metadata.
   Require process success, fresh numeric-zero DumpResult and nonempty artifacts.
2. Inspect the native configuration: managed default mode, no objects except
   language metadata, no roles/default roles and no existing BSL modules. Copy
   original native bytes, including ConfigDumpInfo.xml. Insert only the exact
   role reference into the original Configuration.xml ChildObjects element,
   without XML reserialization or changes to existing UUIDs, namespace, version,
   language metadata or default roles. Generate a fresh UUID only for the new
   role. Add its two XML files and the two existing internal BSL modules.
   The reviewed role serialization is format 2.20; an unknown native format is
   rejected rather than rewritten or assumed compatible.
3. Full LoadConfigFromFiles plus UpdateDBCfg, then re-dump. Require exact role
   identity and the five explicit rights, all defaults false, no other roles,
   defaults, rights, objects or files, and unchanged original configuration and
   language XML semantics. Only insignificant XML formatting, ChildObjects/right
   order and native ConfigDumpInfo.xml bookkeeping may differ. Both BSL modules
   must match, allowing only UTF-8 BOM and line-ending differences. No guessed
   metadata shape or incremental import is used. Source-code specimens establish
   serialization structure, not native runtime success on this image.
4. Start anonymous Enterprise under an exact per-run bootstrap token. The internal
   session hook refuses nonanonymous startup or existing users. It creates the
   one disposable `NativeSmoke` user, observes the actual user-scoped
   `ЗащитаОтОпасныхДействий` type without mutation, and proceeds only if it is
   exactly `ОписаниеЗащитыОтОпасныхДействий` and its
   `ПредупреждатьОбОпасныхДействиях` field is actually Boolean. It changes only
   that existing descriptor's warning flag to false, assigns the descriptor back,
   checks the assigned state, assigns only the known disposable role, verifies
   its exact singleton identity by enumeration, and writes the user. It checks
   persisted FindByName descriptor type and nested Boolean false, standard
   authentication, exactly one user and the same singleton role. The common
   user-check helper requires Contains(the known metadata role), then enumerates
   and uses a scalar counter to reject any second role, never unsupported
   roles.Count or an unmeasured per-element metadata equality assumption. Missing, duplicate or extra
   roles fail before Write or at either readback; unsupported enumeration also
   fails with no fallback. No new
   descriptor resets other settings, and no initial warning value is assumed.
   It does not use an external EPF for bootstrap.
5. Remove the control file. A separate Designer invocation with `/N NativeSmoke`
   must successfully dump metadata and preserve both the injected modules and
   the complete restricted metadata/rights scope under the same strict gates.
6. A separate Enterprise `/N NativeSmoke` invocation must verify both the fresh
   CurrentUser snapshot and persisted FindByName security state, including the
   same exact descriptor type, nested Boolean false and singleton role. Private
   markers must contain exact assigned/persisted/current singleton role arrays,
   where applicable; the host does not publish role metadata. Both bootstrap
   and verification require fresh session and managed-hook markers with exact
   protocol, run nonce, stage, identity, fields and primitive types. Managed hooks
   obtain `SystemInfo.AppVersion`; anything other than `8.3.27.1508` fails.
7. Remove the control file again. With no control file, the session hook does not
   mutate users, and the managed hook ignores the launcher's normal JSON-path
   `/C`. Build/run the unchanged launcher and TestModule templates under the named
   user. The new scenario only reports `native-smoke-v1` and `6 * 7`. Require
   zero DumpResult, both nonempty EPFs, fresh result JSON with exactly `messages`
   and `error`, exact messages `["native-smoke-v1", "42"]`, empty error and exact
   UTF-8/LF output bytes. No broad output normalization is accepted by the gate.

The launcher's existing server-side external-processing creation behavior is
unchanged. No new security bypass, conf.cfg setting, global protection mode,
role-escalation fallback, password, real data or production database is added.
The sole explicit administrative role is limited to this disposable tmpfs base;
its rights are never added to a real database, existing user or global setting.

Module discovery on full import has been demonstrated by byte-identical native
re-export. [The diagnostic run](https://github.com/Atridis/yadinassi/actions/runs/39522764403)
reached the internal session hook and rejected the previous whole-property
Boolean assumption before assigning protection or writing the user. It did not
establish the actual property type. [The descriptor-gated retry](https://github.com/Atridis/yadinassi/actions/runs/39524243345)
then observed `UnsafeOperationProtectionDescription` and inner `Boolean`. Its
matching session error identified unsupported `Количество`, but conflicting stack
locations meant no source line was exported. The earlier GetUsers count had
already succeeded; the role-collection Count check is therefore the likely
remaining failing call, not a proven line-level diagnosis. The subsequent retry
used strict enumeration and reported a generic runtime-error classification
instead; no specific API or line is inferred from that.
The subsequent native Write location established that the old zero-role
iteration completed. The successful role-bearing run cited above later verified
populated role enumeration, persisted/fresh security readbacks, named-user
permissions, actual version and simple EPF. Any compile failure, unsupported API, denied
access, missing hook or modal timeout stops the stage. Do not add broad roles or
weaken protections to turn a failure green. A retry after an attempted bootstrap
requires a newly created disposable database, not another bootstrap against the
partially modified one.

## Bounded public evidence

Only `native-smoke/report.json` is uploaded, with seven-day retention. Container
stdout is capped at 32 KiB and validated as untrusted JSON with exact schemas,
duplicate-key rejection, finite statuses, strict booleans, numeric versions,
known metadata fields and SHA-256 values. Unknown fields or false/inconsistent
success claims fail closed. Native text, paths, UUIDs, image labels/environment,
X cookies, database, XML and logs are never published.

A failed stage keeps its primary orchestration `failure_kind` (for example,
process failure, timeout, invalid marker or module mismatch). A separate strict
`diagnostics` object cannot replace that failure or set any positive gate:

- `native_exit_code` is the directly observed, nonzero code of the failing native
  process, limited to -64 through 255. It is null for timeout termination, missing
  evidence or failures behind the unchanged launcher API; no code is inferred
  from exception text or a prior successful process.
- `category` and `origin` are finite, lossy observations from known phrases, not
  a proven root cause. Categories include compilation/runtime/API errors, denied
  access, authentication/license/training restrictions, startup failure, invalid
  evidence, conflicting evidence and unknown. No automatic workaround follows.
- Only current failing-stage logs and matching session/managed error markers are
  read inside tmpfs, including after a nonzero native exit. Rejected stale evidence
  is never used. UTF-16 and UTF-8 BOMs are decoded strictly; only no-BOM input tries
  strict UTF-8 followed by CP1251. Raw text is never returned.
- Optional single source locations require an exact Russian/English alias for
  the known session or managed module and a line within its exact staged source.
  Optional BSL identifiers must match an explicit finite allowlist and native
  error syntax, including context-method failures. The exact English context
  method name `Write` maps to the trusted source identifier `Записать`; arbitrary
  method names are not exported. A single location comes from category-bearing
  error lines; an identifier can also come from a recognized context-method
  wrapper elsewhere in the same selected source. Thus a specific access or
  authentication cause does not erase its known method wrapper. Conflicting
  locations remain null, while a
  unique observed identifier can survive stack-line ambiguity. This identifies
  observed syntax, not a proven underlying reason for the failure.
- `source_frames` contains at most four unique, validated module/line pairs in
  first-observed order from the one diagnostic source named by `origin`, not a
  union of unrelated logs. It can retain known stack frames on other lines even
  when no single failure location is defensible. `source_frames_truncated` is
  true only if additional distinct known frames were omitted. Unknown modules,
  paths and out-of-range lines never appear. These are observed stack locations,
  not an asserted call hierarchy or selected root cause. Success, stale-evidence
  and conflicting-category reports cannot export frames.
- Marker states are finite. `session_marker="ok"` or `managed_marker="ok"` means
  only that a matching identity envelope reports ok with empty error, not that
  the full user/security/version gate passed. Foreign, duplicate-key, nonfinite,
  malformed, oversized or deeply nested marker input cannot supply details or
  overwrite the primary failure. Success reports have empty diagnostics.

- `rendered_context` is an independent, lossy projection of the entire existing
  bounded `DetailedErrorDescription` string from a valid matching error marker.
  It prefers the session marker, otherwise the managed marker; its own `origin`
  must name a marker whose state is `error`, even when the top category came from
  a native log or reports a conflict. It never reads a log as marker context.
  `representation="detailed_error_text"` does not assert an `ErrorInfo.Cause`
  hierarchy, an exact cause or a reconstructed sentence. The official 8.3.27
  developer guide §31.3.3 describes the current error at the beginning and initial
  cause at the end of detailed error text, motivating preservation of both ends.
- The projection scans the whole private string, not a raw-text prefix. It emits
  only an exact finite Russian/English vocabulary, preserving technical terms,
  negation and requirements in lexical order. No unverified first-administrator
  reason template is inferred. Terms such as transaction, role or license are
  observations, not proof that they caused the rejection. Quoted values, paths,
  URLs, email addresses, named/assigned values, sensitive password/token/key labels
  and authorization values, dotted identifiers and source-frame
  spans become `redacted` before vocabulary matching. Other unknown words become
  `unknown`; adjacent identical unknown/redacted tokens are collapsed. Boundaries
  become `line_break`, `sentence_end` or `clause_break`. This deliberately loses
  opaque text, including technical words inside a quoted role or user name.
  Sensitive labeled values and Bearer/Basic forms redact the remainder of their
  line, even if it resembles an informative technical sentence.
- `head` and `tail` contain at most 64 finite tokens combined. If the projected
  stream fits, all tokens are in `head`, `tail` is empty and `omitted_middle` is
  false. Otherwise the first 32 and last 32 tokens are retained and
  `omitted_middle` is true. Empty/whitespace-only errors, invalid markers, success
  and stale evidence cannot supply context. The unchanged 65,536-byte private
  marker, 8,192-byte stage report and 32,768-byte host report limits still apply;
  tests bound both worst-case serialization and full-limit parsing time. No raw
  descriptions, exception codes, arbitrary identifiers or new native API fields
  are exported. Exception handling remains unchanged; the exact trusted-source
line limit follows the reviewed session module, not a widened text/JSON cap.

The host independently validates diagnostic keys, types, enums, source bounds,
identifiers, provenance and consistency with the failed stage. No native errors,
paths, usernames, UUIDs, raw source fragments or unknown identifiers are exported.

`protection_observation` is separate from success/security gates. A fresh,
identity-matched session marker can report its stage plus finite property/inner
warning types even when the native process fails. The only type values are
`not_observed`, `UnsafeOperationProtectionDescription`, `Boolean`, `Undefined`
and `other`; arbitrary platform type names are never exported. A non-descriptor
property cannot claim an observed inner flag. The type observation is read-only,
before assignment; persisted/fresh false values remain independent required
gates. Invalid, unmatched or stale markers cannot supply a new observation.
An observation alone never means settings were changed or verified. The strict
marker schema rejects the former whole-property-Boolean fixture shape.

`security_change_attempted` and the finite security state distinguish no attempt,
unverified partial execution and verified persisted mutation. The attempted flag
is set before LoadConfigFromFiles because loading role metadata can itself alter
the disposable security state, even when subsequent user creation never runs.
The independent host gate rejects a false no-attempt claim for load, redump,
bootstrap or any later/unknown stage; only an injection rejection can report
unchanged security. The outer
`security_settings_changed` is null when mutation is uncertain, including a
container timeout or invalid/missing report after execution. It is not falsely
reported as unchanged after a partially completed bootstrap.

`simple_epf_completed` means this one deterministic scenario passed.
In bootstrap-only mode, `native_tests_completed` remains false: the broader suite
is not run. Full mode requires its own six-case evidence and comparison gates.
Legacy Windows outputs, existing native observations, launcher and templates are
not changed. `runtime_version_verified` requires the named-session gate, never a
binary path/tag or XML schema inference. Image provenance is the approved training
image; no separate runtime-edition detection is claimed. The report is not an
attestation against a deliberately malicious image.

## Offline verification

These commands do not pull or execute Docker/native 1C:

```
python -m unittest discover -s tests -p 'test_native_1c*.py' -v
bash -n scripts/native_1c_smoke_probe.sh
python integrational_tests/check_launcher.py
python -m unittest discover -s tests -v
```

Coverage includes exact staging, restrictive host umask, containment, registry
authentication separation, fresh markers, Boolean-versus-integer flags, anonymous
identity, exact source-byte preservation except the single role reference,
module-byte preservation, singleton role enumeration and assigned/persisted/fresh
role arrays, strict metadata/UUID/default/right gates before user creation and
before fresh verification, descriptor and nested-Boolean guards, legacy
Boolean-schema rejection, read-only finite type observations, strict
user/version/output gates, named
Designer/Enterprise separation, partial security state and timeout/error paths.
Diagnostic regressions cover nonzero error markers, UTF-16/UTF-8/CP1251, corrupt
BOMs, same-line attribution, contradictory sources, stale evidence, bounded exit
codes, context-method aliases, selected-source stack provenance, frame deduplication
and truncation, finite bilingual context with negation, opaque-value masking,
whole-input head/tail bounds, adversarial parser timing, unchanged serialized-size
caps, malformed marker input and strict host-schema rejection.
POSIX pipe tests and Linux shell tests have platform guards; mocked core gates
run cross-platform. Synthetic XML fixtures are not native/loadable metadata.

## Primary references

- [TigerVNC Xvnc options](https://tigervnc.org/doc/Xvnc.html).
- [1C 8.3.27 administrator guide](https://1c-dn.com/library/tutorials/1c_enterprise_administrator_guide_file_mode_8_3_27/).
- [1C 8.3.27 developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/).
- [Session parameter initialization](https://1c-dn.com/library/using_session_parameters/).
- [Protection-property rename and descriptor distinction](https://downloads.v8.1c.ru/content/Platform/8_3_13_1690/1cv8upd_8_3_13_1690.htm).

- [First-user administrative-role requirement](https://kb.1ci.com/1C_Enterprise_Platform/Tutorials/1C_Enterprise_Platform_Training_Course_-_Senior_Application_Developer_Level/Module_3._Access_rights/Episode_1._Playing_roles/?language=en).
- [1C 8.3.27 rights names and prerequisites, Appendix 5](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/#appendix-5-access-rights-description).
- [Primary-source 2.20 Role XML structural specimen](https://github.com/1Ci-Company/Jet-TR/blob/3f4949d0a5f921309b1b3bae3889910ec063e84a/cf/Roles/FullAccess.xml).
- [Adjacent 2.20 Rights XML structural specimen](https://github.com/1Ci-Company/Jet-TR/blob/3f4949d0a5f921309b1b3bae3889910ec063e84a/cf/Roles/FullAccess/Ext/Rights.xml). Its broad grants and true defaults are deliberately not copied.
- [Official code using InfoBaseUser.Roles.Add with a known metadata role](https://github.com/1C-Company/dt-demo-configuration/blob/1f4b6288a2b22eb11c32b3b2360820e38b66545b/DemoConfDT/src/CommonModules/БотСервер/Module.bsl).
