# Isolated native 1C bootstrap and simple EPF smoke

This is a bounded validation of one approved Linux training image, not the full
native regression suite. The first capability-only run established Python 3.10.12,
non-root execution, dynamic-library resolution, authenticated display startup,
empty database creation and hierarchical configuration export (schema 2.20).
It did not establish the actual application version or user/bootstrap behavior.
The first stage-two native run confirmed full module import, database update and
byte-identical re-export, then failed in anonymous bootstrap with a nonzero process
result. Persisted security state and actual application version remain unverified.
The subsequent diagnostic-only run identified our whole-property Boolean guard
as the failure before protection assignment or user Write. The descriptor-gated
retry then observed the actual descriptor type and inner Boolean, but failed on
an unsupported `Количество` call during bootstrap. This candidate replaces only
the role-collection Count check with fail-closed enumeration. Native commands,
containment and measured descriptor guards remain unchanged. Mock tests are not
evidence that role enumeration or later native stages have passed.

## Invocation and unchanged trust boundary

The temporary workflow `.github/workflows/native-1c-isolated-smoke.yml` still runs
only for changes to the same workflow, its original two helpers or the exact
`scripts/native_1c_bootstrap/**` input directory on the exact
`codex/native-1c-isolated-smoke` branch, in `Atridis/yadinassi`, pushed and retried
by `Atridis`. No PR, fork, main-branch, dispatch, tag or arbitrary-input trigger
is added. The one additional path filter lets reviewed bootstrap-only fixes
trigger another run without widening the branch or actor checks. Remove this temporary route after validation. A helper push triggers
execution and must remain within the approved scope.

The workflow uses both explicit flags:

```
python3 scripts/native_1c_smoke.py --execute-approved-image --bootstrap-simple-epf --output native-smoke/report.json
```

Omitting `--bootstrap-simple-epf` retains the capability-only mode. Both use the
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

Stage two replaces the single probe-file mount with one read-only staged-inputs
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
(capability-only mode remains 480 seconds). The workflow has a 30-minute limit
including image download. Cleanup failure is never reported as success.

## Stage-two gates

All database files, native XML, logs, generated EPFs, request files and markers
remain in tmpfs. There is one fresh database and no concurrent 1C sessions.

1. Create an empty file database and export its native hierarchical metadata.
   Require process success, fresh numeric-zero DumpResult and nonempty artifacts.
2. Inspect the native configuration: managed default mode, no objects except
   language metadata, no roles/default roles and no existing BSL modules. Copy
   native bytes without rewriting UUIDs, schema or ConfigDumpInfo.xml. Add only
   `Ext/SessionModule.bsl` and `Ext/ManagedApplicationModule.bsl`.
3. Full LoadConfigFromFiles plus UpdateDBCfg, then re-dump and compare both modules,
   allowing only UTF-8 BOM and line-ending differences. No guessed metadata or
   incremental import is used.
4. Start anonymous Enterprise under an exact per-run bootstrap token. The internal
   session hook refuses nonanonymous startup or existing users. It creates the
   one disposable `NativeSmoke` user, observes the actual user-scoped
   `ЗащитаОтОпасныхДействий` type without mutation, and proceeds only if it is
   exactly `ОписаниеЗащитыОтОпасныхДействий` and its
   `ПредупреждатьОбОпасныхДействиях` field is actually Boolean. It changes only
   that existing descriptor's warning flag to false, assigns the descriptor back,
   checks the assigned state, and writes the user. It checks persisted FindByName
   descriptor type and nested Boolean false, standard authentication, exactly
   one user and zero roles. The common user-check helper enumerates the role
   collection and rejects the first element; it never adds, removes or ignores
   roles. Unsupported enumeration also fails startup, with no fallback. No new
   descriptor resets other settings, and no initial warning value is assumed.
   It does not use an external EPF for bootstrap.
5. Remove the control file. A separate Designer invocation with `/N NativeSmoke`
   must successfully dump metadata and preserve the injected modules.
6. A separate Enterprise `/N NativeSmoke` invocation must verify both the fresh
   CurrentUser snapshot and persisted FindByName security state, including the
   same exact descriptor type and nested Boolean false. Both bootstrap
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

Module discovery on full import has been demonstrated by byte-identical native
re-export. [The diagnostic run](https://github.com/Atridis/yadinassi/actions/runs/39522764403)
reached the internal session hook and rejected the previous whole-property
Boolean assumption before assigning protection or writing the user. It did not
establish the actual property type. [The descriptor-gated retry](https://github.com/Atridis/yadinassi/actions/runs/39524243345)
then observed `UnsafeOperationProtectionDescription` and inner `Boolean`. Its
matching session error identified unsupported `Количество`, but conflicting stack
locations meant no source line was exported. The earlier GetUsers count had
already succeeded; the role-collection Count check is therefore the likely
remaining failing call, not a proven line-level diagnosis. This candidate uses
strict enumeration instead. Native collection enumerability, persisted and fresh
security readbacks, role-free named-user permissions, actual platform version
and simple EPF execution remain unverified. Any compile failure, unsupported API, denied
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
- Optional source locations require an exact Russian/English alias for the known
  session or managed module and a line within its exact staged source. Optional BSL
  identifiers must match an explicit finite allowlist and native error syntax.
  Location and identifier must come from the same error line as the category;
  unrelated frames, conflicting locations or ambiguous identifiers are omitted.
- Marker states are finite. `session_marker="ok"` or `managed_marker="ok"` means
  only that a matching identity envelope reports ok with empty error, not that
  the full user/security/version gate passed. Foreign, duplicate-key, nonfinite,
  malformed, oversized or deeply nested marker input cannot supply details or
  overwrite the primary failure. Success reports have empty diagnostics.

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
unverified partial execution and verified persisted mutation. The outer
`security_settings_changed` is null when mutation is uncertain, including a
container timeout or invalid/missing report after execution. It is not falsely
reported as unchanged after a partially completed bootstrap.

`simple_epf_completed` means this one deterministic scenario passed.
`native_tests_completed` remains false: the broader integration suite is not run.
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
identity, module-byte preservation, reject-first-element role enumeration,
descriptor and nested-Boolean guards, legacy
Boolean-schema rejection, read-only finite type observations, strict
user/version/output gates, named
Designer/Enterprise separation, partial security state and timeout/error paths.
Diagnostic regressions cover nonzero error markers, UTF-16/UTF-8/CP1251, corrupt
BOMs, same-line attribution, contradictory sources, stale evidence, bounded exit
codes, malformed marker input and strict host-schema rejection.
POSIX pipe tests and Linux shell tests have platform guards; mocked core gates
run cross-platform. Synthetic XML fixtures are not native/loadable metadata.

## Primary references

- [TigerVNC Xvnc options](https://tigervnc.org/doc/Xvnc.html).
- [1C 8.3.27 administrator guide](https://1c-dn.com/library/tutorials/1c_enterprise_administrator_guide_file_mode_8_3_27/).
- [1C 8.3.27 developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/).
- [Session parameter initialization](https://1c-dn.com/library/using_session_parameters/).
- [Protection-property rename and descriptor distinction](https://downloads.v8.1c.ru/content/Platform/8_3_13_1690/1cv8upd_8_3_13_1690.htm).
