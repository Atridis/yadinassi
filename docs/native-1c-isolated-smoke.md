# Isolated native 1C capability smoke

This is a bounded first stage of the approved Linux training-image validation,
not a completed native regression run. It does not replace Windows golden files,
execute integration scenarios, create a test user, or change dangerous-action
protection. A later stage must create and verify the disposable test user and run
the native scenarios before automation can replace manual validation.

## Invocation and trust boundary

The temporary workflow `.github/workflows/native-1c-isolated-smoke.yml` runs only
for source changes to that workflow or its two helpers pushed to the exact branch
`codex/native-1c-isolated-smoke`, in `Atridis/yadinassi`, by `Atridis` (including the
actor who retries it). There are no PR, fork, main-branch, dispatch, tag or
arbitrary-input routes. This narrow push route was selected for the current
approved task, not as permanent CI policy. Remove it after this validation; do not
broaden it as a workaround for a failed run. A push of reviewed helper changes is
itself an execution trigger and must remain within the approved scope.

The host helper requires `--execute-approved-image`. It has one hard-coded image:

```
ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728
```

Registry access uses the job's read-only package token through stdin. The helper
removes it from the inherited environment before Docker commands, deletes the
entire temporary authentication directory after pulling, and creates a new empty
Docker configuration before inspection and execution. Checkout credentials are
not persisted. Neither a token nor the Docker socket is passed into the image.

Execution uses an explicit nonzero numeric UID/GID `1000:1000`, independent of the
image's configured user; this matches the supplied Ubuntu Dockerfile's first
`useradd`. A permission mismatch fails rather than elevating privileges. Image
architecture must be `linux/amd64` and the image must have no implicit volumes.
The inherited entrypoint and healthcheck are disabled. The executable is
`/opt/1cv8t/x86_64/8.3.27.1508/1cv8t`; the path is not runtime version evidence.

The container has no network, published ports, host PID/IPC namespaces, host
writable mounts, or inherited host environment. It gets one read-only probe file,
a clean environment, read-only root, a 1 GiB noexec/nosuid/nodev `/tmp` tmpfs,
128 MiB private shared memory, 2 GiB memory, 2 CPUs, 256 PIDs and bounded file sizes.
All capabilities are dropped and `no-new-privileges` is enabled. Global execution
is capped at 480 seconds, individual native calls at 120 seconds plus a 10-second
kill grace, and the job at 20 minutes including image download. Cleanup is always
attempted; an unverified removal is a failure, never a successful result.

No packages are installed inside the running image. The probe checks Python 3.10+
(the native launcher's minimum), the actual executable and its dynamic libraries.
It starts `Xtigervnc` with an ephemeral Xauthority cookie, RFB TCP disabled
(`-rfbport -1`), no RFB Unix socket, and X11 TCP disabled (`-nolisten tcp`). It does
not disable X authentication or lower VNC security types. It creates one empty
file database and asks native Designer for a hierarchical XML dump. Both process
exit and bounded `/DumpResult` contents must confirm success; required output files
must exist and be nonempty.

## Report and provenance

Only `native-smoke/report.json` is published, for seven days. Container stdout is
bounded at 32 KiB, treated as untrusted JSON, and checked against exact fields,
finite status values, primitive types, bounded numeric versions, fixed schema
namespaces and known property names. Unknown fields, duplicate JSON keys,
malformed output, false success and overclaims fail closed. Stderr is discarded.
The host supplies `container_exit_code`; the image cannot supply that field.

Native logs, database, generated XML, X cookie, binaries and image metadata such
as environment/labels are never printed or uploaded. Native files remain in
container tmpfs and vanish at cleanup. The report includes only fixed capability
flags, native XML schema version/hash/count, presence of documented managed and
session module files, and a fixed allowlist of recognized XML element names. It
contains no native XML text, user names, machine-specific paths or UUIDs.

`smoke_completed` means only capability checks plus empty database creation and
native configuration export passed. `native_tests_completed` remains false.
`runtime_version_verified` remains false, and `runtime_version` is null: no runtime
version is inferred from the tag, binary path, or XML schema version. A subsequent
bootstrap must obtain `SystemInfo.AppVersion` (Russian
`СистемнаяИнформация.ВерсияПриложения`) from the actual Enterprise process, verify
persisted user security flags in a fresh named-user session, and keep Linux
results/provenance separate from legacy Windows golden files.

## Offline verification

These commands do not pull or execute the image:

```
python -m unittest discover -s tests -p test_native_1c_smoke.py -v
bash -n scripts/native_1c_smoke_probe.sh
python integrational_tests/check_launcher.py
python -m unittest discover -s tests -v
```

Tests cover secret/environment separation, auth deletion before execution,
login/pull failure, wrong architecture/implicit volume refusal, execution timeout,
cleanup failure, symlink/directory mount refusal, output flooding, malformed and
extra report fields, incorrect success claims and the exact trigger/artifact
boundary. Real pipe timeout tests are Linux/macOS-only; structural and mocked
checks run on Windows too. The inert fake-tool Bash probe tests are Linux-only
(they use GNU `timeout`). Passing mocks is not evidence that native 1C ran.

## Primary references

- [TigerVNC Xvnc options](https://tigervnc.org/doc/Xvnc.html), including `-rfbport -1`.
- [1C 8.3.27 file-mode administrator guide](https://1c-dn.com/library/tutorials/1c_enterprise_administrator_guide_file_mode_8_3_27/), CREATEINFOBASE, DumpResult and hierarchical DumpConfigToFiles.
- [1C 8.3.27 developer guide](https://1c-dn.com/library/tutorials/1c_enterprise_developer_guide_8_3_27/), native dump module paths and SystemInfo.AppVersion.
