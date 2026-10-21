# Isolated six-scenario native regression

This extends the digest-pinned disposable bootstrap described in
[native-1c-isolated-smoke.md](native-1c-isolated-smoke.md). The real bootstrap,
singleton role/protection readbacks, measured `SystemInfo.AppVersion`
`8.3.27.1508`, and simple EPF passed in
[run 39559544886](https://github.com/Atridis/yadinassi/actions/runs/39559544886).
That bootstrap run did **not** execute the six regression scenarios. Later
[run 39565051736](https://github.com/Atridis/yadinassi/actions/runs/39565051736)
executed all six successfully and preserved their actual bytes, but correctly
failed strict interpreter comparison. Native execution and comparison success
are separate claims; offline replay is not a replacement for a fresh native run.

## Run contract

The default, summary-only and byte-exact invocation is:

```console
python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --output native-smoke/report.json
```

The dedicated approved Docker workflow selects the measured target and Map
comparison contract explicitly:

```console
python3 scripts/native_1c_smoke.py --execute-approved-image --full-suite --native-target linux-8.3.27.1508 --comparison-mode typed-map-order-v1 --output native-smoke/report.json --export-native-outputs
```

The host defaults remain `windows-8.3.27.2342` and `byte_exact`. The typed Map
mode is not selected by the host OS or environment and is unsupported for an
unapproved target/source/build.

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
byte is compared with the accepted native capture. That raw result is always
retained. Only the explicitly selected typed Map contract may separately accept
permitted pair permutations after its stricter framing/type/roundtrip checks.
Nonzero exit, stderr, timeout, missing cases, changed scalar spelling or
significant whitespace differences cannot pass.

The public JSON records finite statuses, sizes, hashes, mismatch positions/counts,
the measured native version, fixed image digest, source provenance, Git
commit/tree and run identity, interpreter/dependency provenance, configured
timezone/locale, security gates and cleanup state. It contains no payload bytes,
raw diffs or arbitrary native error strings. Native execution, evidence
acceptance and interpreter comparison are separate claims. Overall success
requires all six native cases and the selected comparison contract, intact
Windows goldens and verified cleanup. Raw `comparison.status` remains `failed` and affected case statuses
remain `mismatched` for a Map-order difference; separate `acceptance_status`
fields report whether the selected contract accepted it. A semantic acceptance
is never described as byte-exact.

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
raw comparison mismatch is always visible. It fails the byte-exact mode, or
passes only when the explicit typed Map contract independently accepts it.
Either completed outcome may retain this diagnostic artifact; an incomplete
comparison or failed evidence/cleanup gate cannot.

The 32 KiB-bounded `native-1c-outputs-v2` provenance JSON contains only
fixed/schema-checked fields:
measured `SystemInfo.AppVersion`, pinned image digest, UTC/locale, invocation
nonce, commit/tree and optional Actions run identity, interpreter/dependency
provenance (including the Map verifier hash), per-case source/module/native-output
hashes and sizes, the explicit native target/comparison mode, raw mismatch metadata,
and separate finite comparison/acceptance/cleanup status. It contains no raw exception strings or other image,
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

## Explicit experimental interpreter target

The embedding API accepts `Interpreter(native_target="linux-8.3.27.1508")` for
an explicit experimental Linux-amd64 1C 8.3.27.1508 / ru_RU compatibility target.
The existing default is `windows-8.3.27.2342`; omitting the argument preserves
all historical Windows-backed behavior. Unknown names are rejected. The host
OS, environment, locale and Python version never select a target implicitly.
Imports inherit their interpreter's target. Execution scopes restore the caller
on normal exit, errors and reentry; detached copied contexts cannot retain a
finished execution's target. Timezone configuration remains independent.

The Linux target currently changes only two measured collection operations:

- Explicit `FillPropertyValues` include lists are traversed in reverse, with
  per-property validation and immediate assignment. All 72 diagnostic cases
  from native run [39567834362](https://github.com/Atridis/yadinassi/actions/runs/39567834362)
  support this observable rule. This is not atomic prevalidation; exclusions,
  absent lists, fixed-target guards and unsupported domains remain unchanged.
- `ValueTable.Sort` uses an independently authored deterministic introsort model
  with a bounded heapsort fallback. All 96 diagnostic observations (lengths
  15–18) and both original locale cases match the same unchanged UCA6 keys.
  This is an empirical fit for the named target, not proof of 1C's algorithm or
  compiler, a universal Linux rule, or additional native evidence for larger
  inputs. Windows-default stability, supported key domains, limits, row identity and
  validate-before-commit semantics remain intact. `ValueList.Sort` is unchanged.

The verified diagnostic collections output has SHA-256
`9e79c371c74fc0b2f7b9f12c391bf66f635ec3890878d4b8f6b2c72d0f4e9b2d`
at source commit `66ba9dd9f6c96e41c2f4e25394846fe3aa2750b5`.
A strict local replay with the explicit Linux target matches every fill/sort
payload byte and five complete original scenario files. Collections retains
eight historical map-stream ordering differences. Raw comparison therefore
remains different even when the separate approved Map contract is satisfied.
Map hashing, growth and stream order are unresolved. No fixture-key ordering
rules, newly rejected broad map domain or rewritten golden is hidden behind
this target name.

The interpreter CLI and embedding default are unchanged. The dedicated Docker
workflow selects this target explicitly; the host records and checks the selection
against the measured native build. Selecting the target is not a declaration of
universal Linux parity. Historical source/output checks and original Windows
outputs remain preserved; any new target evidence stays separate and is
independently verified.


## Observed Map order and the comparison boundary

The owner approved ignoring entry order for `Map`/`FixedMap` comparison, while
retaining typed keys, their associated values and actual roundtrip checks. This
is a comparison contract, **not** a change to the interpreter's map iteration,
serialization, hashing or supported key domain. Arrays, lists, Structure fields
and table rows remain ordered in this implementation. No Structure-order
difference was observed, so the conditional permission to ignore such a future
difference is not used here.

The decision follows two preserved native diagnostic runs:

- [39567834362](https://github.com/Atridis/yadinassi/actions/runs/39567834362),
  commit `66ba9dd9f6c96e41c2f4e25394846fe3aa2750b5`: all 120 permutations
  of the initial mixed-key family, constructor/readback variants and the
  independent fill/sort evidence.
- [39570458532](https://github.com/Atridis/yadinassi/actions/runs/39570458532),
  commit `6c49bd0add7a2ba7044c33922a120ef2912531c1`: 752 streams with
  7,504 validated typed bindings, 300 mutation states and 1,246 unique labels.
  Its collections output is 589,908 bytes, SHA-256
  `b444be9869353e1ce4bc9155b963ba546dac76bc88f17e7bf6c9de6406b81166`.

All six native executions succeeded in both runs, but strict comparison remained
red. Stream order followed each object's direct iteration, and construction
history mattered: for the N=0/NUBST family the fresh order was SBUTN, while
Clear/refill yielded TSBUN. With N=-1/NUBST, fresh TSBUN became TSBNU after
growth/deletion. Old-key order changed at sizes 17 and 33. These observations
rule out a simple serializer reversal or a rule based only on current keys.
They do not establish a general native hash function or ordering algorithm.

The diagnostic appendices are removed after their raw artifacts were verified.
Their source remains in those commits, while the original collections source
is restored byte-for-byte (245,870 bytes, SHA-256
`70dfefabf9466e1d8d3e00e844f931a7b8f005ed110d74049e07fbfed8fbbc72`).
The new profile tests retain the measured fill/sort coverage; comparator tests
exercise typed map permutations and adversarial non-equivalences without
replacing the original regression scenario or any historical output.

### Typed Map acceptance mode

`typed-map-order-v1` is bounded to the original source hash above and eight
reviewed record labels: the payload and roundtrip payload for
`internal.map.typed-keys`, `internal.map.typed-keys-again`,
`internal.map.reverse-insertion` and `internal.array.nested`. It is not a
universal decoder for 1C's private serialization format. Unknown encodings and
unreviewed source changes fail closed instead of silently expanding the scope.

The verifier parses typed values without converting Boolean/Number/String keys
to colliding Python values. It compares complete key/value bindings with their
multiplicity, not independent sets of keys and values. It does not hardcode the
five fixture keys or their values. Only Map/FixedMap entry order may differ;
type identifiers, scalar spelling, delimiters, ordered nested containers and all
non-eligible output records remain strict. Unsupported references or cycles do
not become equality by omission. The existing identity scenarios remain exact,
including the platform's observed false result for shared-after-change.

Framing is quote-aware and bounded, with complete input consumption. Both the
native and interpreter original/restored values are checked, alongside the
actual `roundtrip.type`, `roundtrip.count` and nested-result messages. Parsing
alone is not treated as a successful native roundtrip. These checks also run
when the eligible records happen to be byte-identical.

A successful semantic result is reported separately from raw comparison, with
its versioned profile, record counts and exact changed eligible labels. The
expected original replay is 750 byte-identical records plus eight permitted
Map-entry permutations, not 758 byte-identical records. Native raw files remain
unchanged in the approved artifact; both raw output hashes/sizes and mismatch
positions/counts remain in the report/provenance. No interpreter output, textual
diff, raw service log or additional artifact file is published by this mode.
