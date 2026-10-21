# Isolated six-scenario native regression

This extends the digest-pinned disposable bootstrap described in
[native-1c-isolated-smoke.md](native-1c-isolated-smoke.md). The real bootstrap,
singleton role/protection readbacks, measured `SystemInfo.AppVersion`
`8.3.27.1508`, and simple EPF passed in
[run 39559544886](https://github.com/Atridis/yadinassi/actions/runs/39559544886).
That run did **not** execute the six regression scenarios. Offline tests of this
extension are not native evidence; a successful full-mode report is required.

## Run contract

The default, summary-only invocation is:

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

By default the six accepted outputs exist only in a private temporary host
directory for comparison and are removed afterward. The explicit diagnostic
export described below is the only exception. Raw native logs, `.err`,
request/result JSON, orchestration exception text, XML, EPFs and the database
are never published. Invalid evidence cannot become a successful
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

## Explicitly approved diagnostic output artifact

Without `--export-native-outputs`, only the finite summary is retained. The
separate flag requires `--full-suite` and exports to one fixed directory,
`native-smoke/native-outputs`; it accepts no arbitrary output path. The dedicated
repository/branch/actor-guarded workflow explicitly opts in for the owner's
approved diagnostic run. Remove that temporary opt-in with the validation route;
do not broaden it to ordinary PR/main runs.

The artifact `native-1c-six-scenario-outputs` has seven-day retention and exactly
seven literal upload paths: `collections.out`, `dates.out`, `functions.out`,
`numbers.out`, `strings.out`, `values.out`, and `provenance.json` inside that fixed
directory. It does not upload directories, globs, archives or raw service logs.
The six files are the exact validated native test outputs, including intentional
scenario error-message strings. No redaction, normalization or interpreter-derived
replacement is applied. Their limits remain 1 MiB each and 2 MiB combined.

Only bounded, verified bytes survive in host memory while the private temporary
directory is deleted. Export requires successful native execution and validated
capture, verified container removal, unchanged historical Windows goldens,
unchanged source/interpreter provenance, and completed private cleanup. A
comparison mismatch still fails the overall gate but may retain this diagnostic
artifact; an incomplete comparison or failed evidence/cleanup gate cannot.

The 32 KiB-bounded provenance JSON contains only fixed/schema-checked fields:
measured `SystemInfo.AppVersion`, pinned image digest, UTC/locale, invocation
nonce, commit/tree and optional Actions run identity, interpreter/dependency
provenance, per-case source/module/native-output hashes and sizes, and finite
comparison/cleanup status. It contains no raw exception strings or other image,
database, XML, EPF or credential contents.

Export is Linux-only and creates a private sibling staging directory using
exclusive descriptor-relative file operations. It refuses symlinks, hardlinked
or special files, unexpected names, changed hashes and any preexisting target.
Linux `renameat2(RENAME_NOREPLACE)` atomically exposes the complete directory,
with no overwriting fallback. Visible directory identities are checked before
and after promotion. The exact seven-file tree and hashes are checked again
immediately before setting the Actions upload-ready signal. A failed export,
changed path, partial write or stale preexisting directory cannot set that signal;
the upload step requires it even when the comparison step exits unsuccessfully.

Historical Windows goldens and `meta.md` are neither replaced nor deleted.
The diagnostics artifact is separate evidence, not a new approved baseline.

## Temporary targeted collection probes

`collections.bsl` temporarily appends `target-probes.v1` after its unchanged
historical body: 120 typed-map insertion permutations plus 24 small key variants,
72 fill/include-list cases, and 96 table-sort observations (lengths 15–18, three
insertion orders, both directions, secondary ID keys and repeated sorts). Raw
map/fixed-map streams and readbacks, typed bindings, every target field after a
fill error, and complete sorted ID sequences with row identity remain observable.
No hash model, prevalidation policy, collation order or sort algorithm is assumed
as a native expectation. Version and operating system changed together between
the Windows and Linux captures, so neither alone explains a difference.

The original 245,870 source bytes have SHA-256
`70dfefabf9466e1d8d3e00e844f931a7b8f005ed110d74049e07fbfed8fbbc72`.
The marked appendix adds no procedures, output files or artifact paths. Its
coverage test executes all six complete sources under the existing 10-second
per-case and 1 MiB/2 MiB output ceilings; this is VM coverage, not native evidence.
Historical full-output/source-integrity checks deliberately remain unchanged and
fail while the extra diagnostics are present. Neither comparator ignores the
appendix. After capturing and reviewing actual native evidence, remove only the
temporary probe appendix and its probe-specific tests/documentation; never
replace or weaken the historical assertions or Windows goldens.
