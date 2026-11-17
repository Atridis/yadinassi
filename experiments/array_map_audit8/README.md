# Audit8: definite Array reads and Map token candidate

Baseline: `f52b1bfacfb965505f86d2efb145f7ff214671d5`.

## Selected change: reuse existing Array proofs

The compiler already proves native Array receivers and callback-free invariant
loops. The same analysis now optionally records known Name nodes and proven For
counters. The module generator consumes those facts as direct reads from the
**same live dictionary**, instead of a repeated get/sentinel/missing-name branch.
There is no value snapshot, Python-locals flush, alias graph, guard or VM fallback.
Existing constructor/authority/opaque-name eligibility stays unchanged. Unknown
effects invalidate the proof. Routine lowering is unchanged; its node IDs are
not consumed as module proofs. The compiler still uses the checked path whenever
presence is not proven. Numeric bounds/exception checks are not removed.

Production diff: eight added lines, two replaced lines in the existing compiler
and Array analyzer. Map production code is unchanged.

## Reproduce

```sh
PYTHONPATH=tests:scripts:. python -B experiments/array_map_audit8/measure.py
PYTHONPATH=tests:scripts:. python -B -m unittest test_python_direct_array_reads
```

Seven alternating pairs, six runs per cell, first run retained but excluded from
warm medians. Every execution verifies the result. Baseline functions are loaded
from the pinned git commit. The old Array specialization stays enabled in both
variants; only propagation of the new presence proofs differs. Map is tested
separately with the baseline Array analysis, so its numbers cannot borrow the
Array improvement. All sources, samples and Python version are in `results.json`.
No concurrent test/reviewer execution ran during timing.

Representative workloads: build/sum 10,000 numeric entries; aggregate through an
Array alias and indexed reads; the same sum in a private routine as an unchanged
control; count 20,000 events into 1,000 numeric or four string Map buckets. These
are computation workloads, not product Save, browser or native-1C measurements.

| Case | Prepared before/after ms | execute(source) before/after ms |
|---|---:|---:|
| Array sum | 9.151 / 7.369 | 16.914 / 10.269 |
| Array alias aggregate | 11.125 / 8.426 | 17.270 / 11.978 |
| Private routine control | 4.494 / 4.675 | 8.561 / 8.732 |
| Map numeric counts | 38.255 / 38.065 | 62.320 / 60.296 |
| Map string counts | 47.141 / 47.314 | 91.480 / 87.438 |

Both Array cases improve in all seven pair medians on both routes (prepared
aggregate reductions ~19% and ~24%). Public execution includes parsing/compilation;
the simpler generated expressions also reduce generated-code work. The private
routine control has no claimed gain; it is about 4%/2% slower in these aggregates
with mixed per-pair variation. No outliers were removed and no universal speedup
is claimed.

## Rejected Map change

The prototype computed `type(key)` once inside `_TypedMap.token` rather than
repeating it along the same exact-type branches. Numeric prepared results differ
by ~0.5%, string prepared regresses slightly, and per-pair results are mixed.
Small public-route differences do not establish a stable Map execution gain.
The production change was discarded; `candidate_token` retains it only in this
reproducer. The original measurement used that same function body provisionally
in the runtime before rejection. No new dispatch specialization or token cache
was introduced to chase the noise. Canonical BSLMap reference-key equality is
untouched and must not be replaced by specialized `_TypedMap` identity semantics.

## Validation and limits

88 tests pass normal and `-O`: new presence-proof regressions, Array specialization,
routine Arrays, definite scalar reads, DB-independent facts, naked collections,
direct default and prepared execution. Independent review: 80 tests `-O` pass,
no blockers. Covered aliases and Clear, callbacks deleting/rebinding variables,
callback changes to counters, byref invalidation, zero-iteration missing names,
partial state on bounds failure, unknown effects and opaque external names.

This is a bounded module optimization. It does not make arbitrary imported arrays,
host callbacks or unknown routine parameters statically safe, and does not change
remaining direct compatibility gaps or claim full CI/native parity.
