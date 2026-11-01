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
