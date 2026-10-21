# Isolated six-scenario native regression

This extends the digest-pinned disposable bootstrap described in
[native-1c-isolated-smoke.md](native-1c-isolated-smoke.md). The real bootstrap,
singleton role/protection readbacks, measured `SystemInfo.AppVersion`
`8.3.27.1508`, and simple EPF passed in
[run 39559544886](https://github.com/Atridis/yadinassi/actions/runs/39559544886).
That run did **not** execute the six regression scenarios. Offline tests of this
extension are not native evidence; a successful full-mode report is required.

## Run contract

The dedicated, repository/branch/actor-guarded workflow invokes:

```console
python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --output native-smoke/report.json
```

Full mode implies the complete bootstrap and simple-EPF sequence in a **fresh**
disposable database. The existing `--bootstrap-simple-epf` mode remains separate.
No earlier database, markers, native capture, or interpreter output can satisfy
the new run's gates.

After those gates, the unchanged launcher builds and executes the complete six
public sources in this fixed order: `collections`, `dates`, `functions`,
`numbers`, `strings`, `values`. Each case uses a fresh test EPF and named native
session. Successful process exits alone are insufficient: fresh build results,
EPFs, strictly parsed result JSON, empty uncaught-error field, source identity,
and actual output bytes are checked. Expected errors intentionally caught and
reported by a scenario remain part of that scenario's exact output.

The image digest, executable, scoped role and security readbacks are unchanged.
The read-only input allowlist grows from 16 to exactly 23 files: six sources and
one trusted full-suite helper. It still excludes the repository, `.git`, Windows
goldens, credentials and the interpreter. The container has no network, ports,
Docker socket, host-writable mount, or tokens; the database and native logs stay
in bounded tmpfs. Full mode has a 2,400-second container ceiling, the workflow a
60-minute ceiling, and each native process retains its 120-second timeout.

## Actual bytes, private transport

Native output means the exact `.out` bytes saved by the unchanged launcher from
actual native message values: UTF-8 without BOM, the launcher's established
CRLF/CR-to-LF conversion, and one LF after each message. No additional trimming,
normalization, substitutions or interpreter-generated reference data is allowed.

While tmpfs still exists, the trusted wrapper emits a private, bounded envelope
with a fresh host nonce, the finite report and exactly six fixed output entries.
The host captures it without printing it. Limits are 1 MiB per decoded output,
2 MiB combined, and 3 MiB for the entire transport; the native finite report
retains its separate 32 KiB bound. Exact schema/order, duplicate keys, types,
canonical base64, lengths, hashes, nonce and all 23 host-known source hashes are
validated. Failure envelopes carry no output payloads. No archives are extracted
and no arbitrary container path is copied.

The six accepted outputs exist only in a private temporary host directory for
comparison. They are never uploaded or committed by this workflow. Raw native
logs, `.err`, request/result JSON, bootstrap exception text, XML, EPFs and the
database are also not published. Invalid evidence cannot become a successful
reference set. Cleanup failure prevents an overall success claim.

## UTC comparison and provenance

The interpreter runs **outside** the native container, in a fresh bounded
subprocess for each complete source, with `YADINASSI_TIMEZONE=Etc/UTC`,
`TZ=Etc/UTC` and UTF-8 output. The same message serialization is used, then every
byte is compared with the accepted native capture. Nonzero exit, stderr,
timeout, missing cases or significant whitespace differences cannot pass.

The public JSON records finite statuses, sizes, hashes, mismatch positions/counts,
the measured native version, fixed image digest, source provenance, Git
commit/tree and run identity, interpreter/dependency provenance, configured
timezone/locale, security gates and cleanup state. It contains no payload bytes,
raw diffs or arbitrary native error strings. Native execution, evidence
acceptance and interpreter comparison are separate claims. Overall success
requires all six native cases and byte comparisons, intact Windows goldens and
verified cleanup.

The owner-confirmed Windows `8.3.27.2342` outputs and `meta.md` remain immutable.
Their existing `Europe/Warsaw` replay tests are not repurposed as Linux/UTC
evidence. Differences across versions/platforms are findings to investigate,
never a reason to overwrite old goldens or silently normalize a mismatch.

The workflow uploads only `native-smoke/report.json`. Publishing any genuine
native `.out` capture would be a separate, explicitly scoped operation.
