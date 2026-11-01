# Test execution deduplication

This is test-only execution reduction, not removal of historical/native oracles.
No interpreter, integration BSL, historical source pin or native output changes.

## Coverage map

| Previous execution | Retained coverage |
| --- | --- |
| `FillIncludeCheckpointTests.test_each_target_keeps_all_828_old_records_and_observes_partial_mutation` | New `FillHistoricalReplayMatrixTests`: exact 828→841 prefix, all 13 INCLUDE labels/shapes, Windows/Linux partial-mutation differences. |
| `FillExcludeCheckpointTests.test_full_current_source_preserves_every_old_record_for_both_targets` | Same matrix: exact 841→852 prefix, all 11 EXCLUDE labels/states including target-specific source-only behavior and both successful controls. |
| `FillExcludeOrderCheckpointTests.test_full_841_and_852_prefixes_survive_on_both_interpreter_targets` | Same matrix: all 841/852/current prefixes, original counts, old last-only position, two source-order labels/shapes and default-target restoration. |
| Full helper-prefix setup in each cache instrumentation instance | Exact unmodified source text of 18 routines: 9 cache probes, 4 dependencies, observer and 4 final-empty probes. Fresh VM, weak keys, hooks, mutation paths and every original test remain. |

Four distinct historical sources × two targets now execute once each (8 instead
of 14); no output cache and no replacement of old execution with current prefixes.
The three old replay tests become one; two new dependency guards keep the scoped
count at 49 tests (12 fill and 37 cache/final-empty). All inverse/hash/fail-closed,
synthetic discrimination and independently audited native-854 replay tests remain.

The helper fixture shrinks from 189,317 characters / 155 routines to 13,993 / 18.
A guard compares extracted routines with full-prefix semantic ASTs, checks static
callee closure, both dynamic observation bodies, the sole indirect evaluation,
and absence of used globals or module initialization. Negative controls cover an
omitted dependency, new top-level initialization and changed final-empty dynamic
root. Existing full-source parse/declaration checks remain; selected synthetic
policies do not establish native 1C cache semantics.

## Validation and measured scope

Paired local Python 3.12.14 / Linux subprocess measurements, with the same
pinned dependency environment and source-hash checks before/after each run:

| Workload | Before | After |
| --- | ---: | ---: |
| Three full-replay methods → consolidated matrix | 95.19 s | 54.13 s |
| Cache + final-empty modules (35 original tests → same 35 + 2 guards) | 156.65 s | 16.08 s |

The cache comparison runs every original synthetic policy, fault, mutation,
weak-reference and GC assertion against both the full-prefix baseline and the
minimal actual-source fixture. The original 35 test methods are unchanged. All 49 affected tests pass in normal and optimized (`python -O`) modes. An
independent review checked retained replay assertions and helper closure.
These are local focused timings, not a whole-suite or native-1C speedup claim.
Full platform CI remains the release gate; native inputs and native fixtures are
byte-identical, so this test-only change does not require a new native capture.

The stacked candidate is based on PR #148 head
`ca0bfa6267509ce0248a39ba98258bf927f5337d`; the timings above remain measurements
of the preceding main baseline and the isolated optimization, not a rerun on
this union. All scripts, interpreter modules and integration inputs are
byte-identical to that PR #148 head. Its native evidence is therefore inherited,
not newly captured by this test-only PR. Four-platform build/test CI runs on the
stacked PR; the native workflow's main-base restriction is unchanged. Retargeting
to main after #148 merges does not itself constitute fresh native evidence.

## Native collections console transport sampling

The collections binary smoke retains the complete historical source and exact
owner output through BOM/Cyrillic/spaced file and stdin: 4,579 output lines,
including all 142 table observations. Console now reuses the existing eight
native command observations and unchanged multiline helpers, followed by
`/exit`. The `-c`, Cyrillic `-с`, and `--command` samples are unchanged. All six
routes retain exact stdout, empty stderr, zero exit status and the 30-second
limit; command routes retain the Windows UTF-16 argv-size guard.

The sample covers table/column codecs, column properties/addition, selected
copy, fixed strings, nested sharing and object graphs. Console still exercises
multiline declarations, UTF-8 and persistent state. Explicit tradeoff: the other
134 table observations and preceding collections families no longer run through
console in their complete historical sequence; this checkpoint no longer tests
the long whole-corpus incremental-input workload. Full semantic parity remains
file/stdin; dedicated CLI tests cover multiline state and error/EOF recovery.

Focused tests verify transport inputs, complete native records, pinned sample
source/output hashes, all exit/stdout/stderr failures and timeout propagation.
Native fixtures, source reconstruction and interpreter code are unchanged. This
is not evidence of a Mac timeout cause or a frozen-binary performance fix; fresh
platform binary CI remains required.

On the isolated main-based candidate, 19 targeted tests passed both normally and
with `python -O`. A single local Linux interpreter replay through the actual
smoke helper passed all six exact-output checks: file 3.569 s, stdin 3.718 s,
console 1.119 s, and command aliases 0.281 / 0.281 / 0.314 s respectively.
These are individual interpreter timings, not a before/after benchmark, a
whole-suite pass or frozen Mac binary validation.

## CRLF transport and finite-budget filesystem deduplication (2026-11)

This test-only follow-up keeps all production serializers, validators, source
hashes, native fixtures and limits unchanged. It does not cache source inventories
or interpreter results. CLI semantic × transport coverage is deliberately left
unchanged in this checkpoint.

| Previous execution | Retained coverage / explicit tradeoff |
| --- | --- |
| CRLF checkout test recursively rediscovers whole Load/Rows/Columns suites, including 382 `smoke.main` calls | Real full staged CRLF checkout, actual `smoke.main`, both byte-exact and typed-map summary modes, three diagnostic families, endpoint/interior tokens, malformed/mixed packets: 22 explicit calls. Complete 28 Load and 81 + 81 Rows/Columns vocabularies, every semantic mutation, source tamper and all original normal-checkout orchestration tests remain unchanged. The exhaustive vocabulary × CRLF cross-product is no longer repeated. |
| Every finite async wire sample creates a directory and binary report file | Each sample still calls the unchanged production `write_report`, encoder, validation and cap; only its binary destination is an in-memory test sink. The complete finite enumeration remains. Dedicated tests compare disk bytes with sink bytes, exclusive-create collision behavior and cap-before-open at exact boundary. Public-summary CLI text writes and CRLF newline simulation remain real filesystem operations. |

The sink accepts exactly one `xb` open and retains exact bytes; it neither
reserializes JSON nor normalizes line endings. Production checks execute before
its destination is opened. No production function or validator is patched out.
The explicit cap boundary test temporarily lowers the real cap in its own scope
and verifies rejection before open, then exact-boundary success.

Tests use scoped temporary directories and the existing synthetic filesystem
adapter. Measurements are sequential, not a parallel full-suite experiment.
Do not infer safe parallelism for other tests using shared `/tmp/onec-smoke` paths.

Paired local Linux / CPython 3.12.14 timings, same pinned environment and source
base tree `537a62c66adebf180b79b5f48d7a1a9957a8308c` (merged main
`273d40ab0abb3fad2a4489ba2cefa100c189dfc8`):

| Two affected modules | Before (22 tests) | After (24 tests) |
| --- | ---: | ---: |
| Normal Python, subprocess wall time | 76.394 s | 53.706 s |
| `python -O`, subprocess wall time | 72.434 s | 47.274 s |

These are single sequential before/after observations (about 30% / 35% less time
in this subset), not a CPU profile, whole-suite estimate or cross-platform
speedup guarantee. Two new transport/cap tests are included in the after timing.
The separate unchanged Load calibration / Rows / Columns suites are also checked
in both modes; no full aggregate or native capture is part of these local timings.
Full platform CI remains required. No native input or production runtime changed,
so this test-only change does not require new real-1C evidence.

## CLI diagnostic-message transport matrix (2026-11)

Five error families previously reran every expression through all six routes.
Each expression still runs in a fresh process through `-c` and through the
stateful console, preserving its exact diagnostic/location, nonzero exit,
stdout, absence of traceback, and console-state recovery assertions. For each
**distinct expected diagnostic text within each family**, its first expression
still runs through all six routes: `-c`, Cyrillic `-с`, `--command`, BOM file,
stdin, console. The selector is reset for every family and stores only diagnostic
text, never execution results, source hashes or interpreter state.

| Error family | Expressions / distinct diagnostics | Previous calls | Retained calls |
| --- | ---: | ---: | ---: |
| Date | 20 / 12 | 120 | 88 |
| String template | 4 / 2 | 24 | 16 |
| String boundary | 8 / 1 | 48 | 20 |
| Character | 4 / 1 | 24 | 12 |
| Rounding | 5 / 2 | 30 | 18 |
| Total | 41 / 18 | 246 | 154 |

Explicit tradeoff: **expression × six transports is no longer exhaustive** in
these five methods. Expression × command/console and diagnostic text × six
transports remain exhaustive. This does not claim that identical messages prove
identical language semantics; both command and console still execute every
semantic case independently. The coverage guard checks these two products and
the exact 154-call matrix, and rejects truncated/reordered route lists.

All success programs still run through all their original routes. Command alias,
escaping/Unicode, BOM/cp1251/file-path, stdin, lexical/parse errors, imports,
argument conflicts, missing files/encodings, EOF and interactive console/history
checks are unchanged. So are all other error families and every original fault
assertion. No interpreter, subprocess timeout, smoke script, native fixture or
production validator changes; no process sharing or subprocess-output cache.

Sequential local Linux / CPython 3.12.14 measurements on main
`72833c952433a258033d8c95bf94a62577542275` (tree `1c68bc87…`), same environment:

| Measurement | Before | After |
| --- | ---: | ---: |
| Whole `test_cli`, normal runner wall time | 74.906 s / 88 tests | 68.802 s / 89 tests |
| Whole `test_cli`, `-O` runner wall time | 75.735 s / 88 tests | 64.549 s / 89 tests |
| Five changed methods, normal per-test time sum | 25.752 s | 17.279 s |
| Five changed methods, `-O` per-test time sum | 26.294 s | 15.843 s |
| Whole-module `run_cli` calls | 628 | 536 |

Both final 89-test runs passed without skips. `-O` applies to the unittest
runner; the unchanged helper launches CLI subprocesses normally. The extra test
is the pure coverage guard. All original 89 methods (including `run_cli`) were
also structurally compared with the base: after removing only the new local
`seen_messages` initialization and route-selection assignment, their ASTs are
identical. No original assertion or subprocess option was altered.

These single paired observations show about 8% / 15% less whole-module wall time,
not a whole-suite or all-OS guarantee. Unchanged tests also varied in duration;
the deterministic reduction is 92 fresh CLI launches. Full platform CI remains
required. No native evidence needs reacquisition for this test-only change.

## Full CI per-test timings

The main four-platform test step uses `python -m scripts.run_tests discover -s
 tests -v` (on one line). This delegates discovery, filtering, fail-fast, buffering,
result classification and exit status to `unittest`; it does not select a smaller
suite or retry tests. Each completed verbose test gets one line, for example
`test_example (test_example.Example.test_example) ... ok ... 1.234 s`.

A monotonic `perf_counter` measures `startTest` through `stopTest`, including that
case's setup, teardown and cleanups. Discovery/imports and module/class fixtures
are outside these individual timings; a class fixture error retains the ordinary
unittest diagnostic without an invented duration. Subtest failures/errors/skips
are summarized on their parent test's timed line, with their original detailed
failure diagnostics retained. Timing is not a CPU profile. Finished lines are
emitted after cleanup, so a running/hung test has not yet printed its status line.

The runner retains only the slowest 20 timing entries and prints their full test
IDs after the ordinary summary. Default dot verbosity remains dots plus the
slowest summary; quiet mode remains quiet. Test stdout/stderr is not intercepted
beyond unittest's existing optional `-b` buffering. The standalone standard
`python -m unittest ...` command remains available and unchanged.

The existing actual CPython 3.10 compatibility job also runs the nine small
runner tests normally and with `-O`; no new matrix or full-suite repeat is added.
