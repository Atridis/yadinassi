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

## Temporary bounded map-family experiment

The first `target-probes.v1` appendix has been removed after its native capture
at commit `66ba9dd9f6c96e41c2f4e25394846fe3aa2750b5`. Its data does not yet
establish a general native map hash, growth, iteration or serialization contract.
The second appendix, `target-map-family.v1`, is a bounded falsification experiment,
not a fixture-shaped runtime rule, replacement golden, or claim of hash recovery.

The five independently typed base keys are U=Undefined, B=false, N=a number,
S="0", and T=Type(Number); values are unique string IDs U/B/N/S/T. It observes:

- 144 fixed-size cases: all 61 integers -30..30 plus -1.5, -0.5, 0.5, 1.5,
  13.5, 26.5, 4294967295, 4294967296, 4294967297, 18446744073709551615 and
  18446744073709551616, each inserted in NUBST and NBSTU order. Fraction and
  boundary labels spell these out as `minus1p5` through `plus26p5`,
  `u32-minus1`, `u32`, `u32-plus1`, `u64-minus1`, and `u64`.
- Four growth histories: N=0 or -1, each in NUBST and NBSTU order. Numeric
  filler keys 2..60 have independent IDs F2..F60 and grow each map from 5 to 64
  entries. Direct For Each ID sequences are recorded after every insertion,
  including the first four. Raw checkpoints are sizes 5, 13, 14, 29, 30, 59,
  60 and 64, deliberately spanning candidate growth boundaries without assuming
  that any particular bucket counts or hash arithmetic apply.
- After growth, delete fillers in order 60..2 and capture the remaining five;
  Clear the same object, record its empty count and reinsert the same five;
  then create a fresh five-key map in the same order. Capture each final state
  and direct iteration after every reinsertion. This preserves deletion,
  allocation-history and Clear-vs-fresh contrasts instead of flattening them.

Each of 188 checkpoints retains four exact internal streams: the mutable map,
its readback, FixedMap(map), and the fixed readback. One compact summary reports
all four direct For Each sequences, counts and type checks, plus typed lookup
and entry-association checks against independent key and ID arrays. The raw
streams remain byte-observable; the probe never sorts or normalizes native
payloads. Coverage tests require complete unique labels and the correct typed
bindings, but deliberately assert no iteration order or serialization order.

This grid tests numeric sign/fraction/word-size and growth/history hypotheses;
it does not cover every scalar or object-key family. A native capture must be
reviewed before deciding whether a general mechanism is supported or what
bounded experiment is needed next. Version and operating system changed together
between the historical Windows and newer Linux captures, so neither alone
explains a difference. No runtime/profile implementation is included here.

The original 245,870 source bytes remain the complete prefix, with SHA-256
`70dfefabf9466e1d8d3e00e844f931a7b8f005ed110d74049e07fbfed8fbbc72`.
The marked appendix reuses existing helpers and adds no procedures, output
files or artifact paths. Its coverage test executes all six complete sources
under the unchanged 10-second per-case and 1 MiB/2 MiB output ceilings, with a
stricter 750,000-byte collections VM guard. This is VM coverage, not native
execution evidence. Historical full-output/source-integrity checks deliberately
remain unchanged and fail while the diagnostic appendix is present. Neither
comparator ignores the appendix. After actual native capture and review, remove
only this temporary appendix and its dedicated test/documentation; never replace
or weaken the historical assertions or Windows goldens.
