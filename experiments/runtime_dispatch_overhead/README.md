# Runtime dispatch overhead, 2026-11-16

Implementation: `442135e5ef3109e3ab88afcb5e7b116ba04f91d1`, tree
`fb94d2a52e544042297c78c5c5b05e6606bb6edd`. Baseline:
`127df054ba7a9ab930b25d9fa4ff080dd2ffa38e`. Both were clean for all samples.
This evidence-only follow-up does not change measured runtime or tests.

The implementation retains lazy import boundaries but caches a closed set of
module handles, reading symbols live. Initializing/failed imports are not cached.
It also replaces the static tail of type lookup with exact type identities and
removes duplicate private syntax-kind lookup while checking live provenance.
No grants, receivers, VM state or callable values are cached. Module unloading or
replacement in sys.modules/custom import hooks on cache hits is not supported;
this is not a Python sandbox. BSL rights, budgets, byref and explicit oracle stay.

## Measurement

40 sequential fresh-process samples, explicit backend constructors; six unchanged
native fixtures. Strict order ABBA for each scenario, plus BAAB for collections;
one interpreter control per source/scenario. A=baseline, B=candidate. Each process
used `-I -B -X pycache_prefix=<new empty temporary directory>`. Run measure.py with
arguments ROOT BACKEND SCENARIO using that command. Total is import/init + parse +
execute_program (including initial preparation), not subprocess launch time.
Timeouts were 55s strict/35s oracle solely for observations, not acceptance limits.
The original production 20s collections gate was separately retained and tested.

| Strict workload | Baseline median, s | Candidate median, s | Change |
| --- | ---: | ---: | ---: |
| collections (4 each) | 25.4660 | 23.1376 | -9.14% |
| functions (2 each) | 1.9702 | 1.9284 | -2.12% |
| values (2 each) | 3.7256 | 3.5982 | -3.42% |
| numbers (2 each) | 1.5446 | 1.5504 | +0.38% |
| strings (2 each) | 1.4305 | 1.3171 | -7.93% |
| dates (2 each) | 1.1348 | 1.1054 | -2.60% |

Collections ranges: baseline 24.1084–27.7464s, candidate 22.3323–23.9803s.
Shared unpinned host, only five CPUs in affinity; small samples and drift limit
generalization, especially short workloads. No concurrent test/profile jobs
were launched during measurements. Environment and CPU times are recorded.
Local wcwidth 0.9.4 differs from CI's 0.8.2; both local sources used the same venv.

All six outputs are byte-identical across both sources and explicit interpreter.
Collections: 265336 bytes, SHA256
`656a4c6af0e31535841f073cba3705e5f16096dd8f910541b3f441f60c055297`.
Strict translated counters are positive; recorded fallback/rejection/helper
counters zero; interpreter compiler stats empty. Unavailable legacy counters
are not evidence of zero executions. This is local equivalence, not native parity.

Original strict gate still **FAILS**: `interpreter_timeout`, 20.00907344s (generic
harness error name despite explicit compiled-strict). No caps changed. Strict
remains slower than interpreter (collections controls 11.3180s / 9.5764s).
This is a modest measured overhead reduction, not near-direct-Python performance.

samples.jsonl SHA256:
`edb480043013161a94d3144c05eccefce7b44fc27637dcb74df582ead9e4156c`.
measure.py SHA256:
`2bcef7cb97cec9e067e892f122ae3d85db3671fb8007f8381be77fb83dd9fb10`.

## Validation and limits

Implementation source: 342 targeted contract/security/source-context tests PASS
(12.139s); 396 compiler/owned-syntax/runtime tests PASS (28.079s). Suites overlap;
counts must not be added as unique coverage. Independent reviewer: 47/47 PASS
(1.461s), including all 13 new tests, no concrete blocking findings. Tests cover
live rebindings at receiver/argument boundaries, revocation in both backends,
GC/lifetime, partial imports, exact-type lookup and forged syntax identities.
Partial import test simulates loader responses rather than real cyclic modules.
No full/heavy suite or workflow was run for this change. Offline executor's
unpublished direct-lowering/synchronous-host work remains of unknown availability.
