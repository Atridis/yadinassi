# Explicit executable entry and whole-unit role admission

Baseline `777bdb3a5c55543751a6b13b743e2bb808217c65`.
Implementation `532add2720b4278ef6a2adfebd678a1b32a44fa9`, tree
`f955cd5f5ded7dab4f50bcf9ff71aa92d3641bb7`. This evidence-only follow-up
does not alter tested runtime or tests. All measurement sources were clean.

## Actual migration blockers versus separate goals

The audit did not identify an absent ordinary parser-produced statement or
expression kind in the current FORCE lowering. That static observation is not a
claim of complete BSL/native compatibility. Concrete embedding admission defects
are reproduced on both exact sources in the saved JSON/script:

| Case | Baseline | Candidate |
| --- | --- | --- |
| Public visit of an admitted nested Assign | node-adapter rejection | generated entry executes x=1 |
| Host(); assignment with Literal target | rejects after 1 host effect | rejects before any effect |
| Host(); assignment with OmittedArgument value | rejects after 1 host effect | rejects before any effect |

The public visit boundary now distinguishes metadata from executable capability
and explicitly prepares the missing entry. Internal run_node/run_block remain
fail-closed, without runtime compilation or hidden fallback. Whole-unit role
checks run at admission once per unique node, after caps/dedup. Metadata-only
nodes cannot become generated statements. ServerInitializer metadata, its body,
and the filtered module entry remain distinct. Standalone expression research
helpers retain their delayed-error contract.

This is a correctness package, not the next proven speedup. Shared vm.call,
generators, residual/compact routes and repeated routine metadata work remain
performance/migration debt; this package does not claim to remove all such work.
Strict collections20s is a separate unmet performance gate. Documented limits
remain: cross-context non-Val actuals require named variables; inactive-block
jumps are unsupported; mutable+production FORCE rejects explicitly and does not
fall back. Documentation now states that combination honestly. Native map-order
acceptance and other scoped comparisons are not universal byte-exact parity.

## Verification

514 focused tests PASS28.512s on the final implementation: compiler/owned/private
identity, source/context, byref/invocation, lifecycle, source binding, budgets and
eight new entry-admission cases. Shared-node validation has a regression test.
Independent review found no remaining blocking issue:26 tests,18 tests and final8
tests PASS (overlapping sets, not additive unique coverage), plus malformed-role
and shared-graph probes. Final committed diff and benchmark source binding were
independently audited. No full/heavy, Ready or merge was run.

## Repeated measurements and limitations

36 sequential fresh-process samples: strict ABBA per each of six unchanged
fixtures, then explicit interpreter controls per source/scenario. Total is
import/init + parse + execute_program, including preparation, excluding process
launch. -I -B and a new empty pycache prefix for every subprocess. Scripts preserve
machine-local paths. Shared unpinned host, Python3.12.14, identical venv for both
sources; no concurrent test/profile jobs launched during measurements. See raw
CPU times, environment, fixture/runtime hashes, outputs and counters.

| Strict workload | Baseline median s | Candidate median s | Change |
| --- | ---: | ---: | ---: |
| collections | 22.927780 | 23.266199 | +1.48% |
| functions | 1.855929 | 1.907572 | +2.78% |
| values | 3.460363 | 3.391019 | -2.00% |
| numbers | 1.540773 | 1.474220 | -4.32% |
| strings | 1.363864 | 1.419130 | +4.05% |
| dates | 1.123431 | 1.084386 | -3.48% |

Two strict samples per source/scenario do not establish a stable regression size
or speedup. Collections ranges overlap (baseline22.3021–23.5535s,
candidate22.8203–23.7121s). Results are mixed; no speedup is claimed. All six outputs
are byte-identical across sources and explicit interpreter. Recorded strict
fallback/rejection/helper counters zero and translated counters positive;
interpreter compiler stats empty. Unavailable counters are not measured zeros.
Local equality does not establish native compiled parity.

Original production collections gate still FAILS:20.008120s,
`interpreter_timeout` (generic harness string; backend explicitly compiled-strict).
Gate JSON includes exact commit/tree, clean status, limit20, fixture and harness
SHA256. Observation timeouts55/35s only permit measurement, not acceptance.

Raw samples SHA256:
`54de12e425a6245c65dac297fed0b6cdf19535b8830026da66a8901d4fc4c593`.
checksums.json covers saved files. Owned-dispatch39e162/abef9a remains excluded;
offline executor's unpublished work remains of unknown availability.

Next substantive migration target: prepare immutable routine/argument entry
metadata at admission while retaining live routine selection, source ownership,
rights, version/registration checks, budgets and byref effects on each invocation.
It must be measured independently; no removal of guards is justified by this data.
