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
