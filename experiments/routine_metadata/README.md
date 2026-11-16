# Prepared routine and formal-argument metadata

Baseline `039ac32b168fa8b5d5c63bd3aef284eaaec54d98`.
Implementation `933ae60966f7221c73893cfd91a69a8be56850c2`, tree
`9e298819421f4944592ab1b97a8cb26776b1c5ea`. Both measured sources were clean.
This later documentation/evidence commit does not change runtime or tests.

## Migration scope and live boundaries

Owned snapshot plans now retain immutable formal-parameter layouts: normalized
names, by-value flags, default nodes, required arity and byref positions. Label
validation is performed after bounded graph admission, rather than walking the
routine body on every call. A direct invalid routine retains only four diagnostic
scalars (no exception/traceback), replayed at the former label-check point after
live context/arity checks. Normal execute_program still rejects invalid labels
before effects.

No permissions, selected callable, receiver, storage or argument values are cached.
Current family/context/rights checks, source-bound owner admission, post-actual
owner verification, caller admission of foreign defaults, copyback and budgets
remain in place. Actual-argument shape/group classification and live binding are
not migrated by this package. Mutable/legacy paths retain their explicit behavior;
production FORCE+mutable remains rejected without interpreter fallback.

Each layout reserves8+6×parameter-count slots against the existing aggregate
MAX_REGISTRY_ENTRIES cap before allocation. Shared Parameter lists do not evade
the charge. Nested admission reconciles final replacement deltas; outer failure
rolls back charge with journals. Release drops layouts/charge together with plans.
No cap is raised. The allocation charge can reject a previously near-cap unit;
that is explicit resource accounting, not a claim of unlimited compatibility.

## Tests and independent review

572 focused tests PASS31.461s on exact933ae609. Eight new tests cover repeated
calls without runtime label walks, shared-list budget rollback, owner revocation
between actuals, caller-owned defaults, arity-before-label diagnostics, release/GC,
snapshot mutation and nested same-layout accounting/rollback. Existing context,
byref, invocation, reusable-values, transient units and compiler suites are included.
Independent review68 tests PASS plus nested probes; final committed diff and
source-bound evidence audited without a remaining critical finding. These are
targeted tests, not full/native compiled parity.

## General six-fixture benchmark: no demonstrated overall speedup

44 sequential fresh-process samples: strict ABBA for six scenarios, additional
BAAB for collections/dates, one explicit interpreter control per source/scenario.
Each uses -I -B and a new empty pycache prefix. Total includes import/init, parse,
and execute_program/preparation; subprocess launch is excluded. Same Python3.12.14
venv and shared unpinned host, no concurrent tests/profile runs. Paths in scripts
are retained as executed. Small samples and host drift limit inference.

| Workload | Baseline median s | Candidate median s | Change | Strict samples/source |
| --- | ---: | ---: | ---: | ---: |
| collections | 23.223023 | 23.291596 | +0.30% | 4 |
| functions | 1.949589 | 1.967395 | +0.91% | 2 |
| values | 3.517302 | 3.523511 | +0.18% | 2 |
| numbers | 1.542753 | 1.569811 | +1.75% | 2 |
| strings | 1.434117 | 1.438403 | +0.30% | 2 |
| dates | 1.164026 | 1.215169 | +4.39% | 4 |

Dates increased9.56% in initial ABBA but decreased in reverse BAAB; the combined
result is not evidence of a stable regression size or improvement. Collections
ranges overlap: baseline23.0332–23.8931s, candidate22.8109–23.6750s.
All six outputs match across sources and explicit interpreter. Recorded strict
fallback/rejection/helper counters zero; translated counters positive; interpreter
stats empty. Unavailable counters are not measured zeros.

## Narrow synthetic benchmark: benefit for repeated label walks

The saved fixture calls a function5000 times. Its false branch contains200
assignments; labels validation previously walked them on every invocation even
though they never execute. This deliberately targets the migrated work; it is
not representative of all BSL workloads and was added after the general series.

Strict ABBA+BAAB, four samples/source: total median1.497255→1.247970s,
**−16.65%**. Execute median0.928985→0.652312s (−29.78%). The reported headline
uses total, including admission cost. Two additional explicit interpreter controls
produce the same output; all10 samples output SHA256
`fa75c3c0aa09ad0f0748d0ef5b98fb706c7d94523a4fc2a6af7e0644a7d86f44`.
This scoped benefit must not be substituted for the neutral six-fixture result.

## Remaining gates and work

Original strict20s collections gate still FAILS at20.008144s. Gate JSON binds the
clean exact commit/tree, fixture, harness SHA, backend and unchanged limit. The
generic harness string is interpreter_timeout despite explicit compiled-strict.
Observation timeouts55/35s only allow measurement, not acceptance.

No full/heavy, Ready or PR merge was run. Prior CI results must not be attributed
to this source. Actual-argument lowering, generic semantic services/generator
overhead and general performance remain further work; this does not remove live
checks or establish full1C compatibility. Owned-dispatch39e162 remains excluded.

General samples SHA256:
`69b4f6da79238c0667060bd94ca31d54c0086a1c5b150fad3255abebf7dc1cc3`.
checksums.json covers raw samples, scripts, gate, fixture and test log. Offline
executor work remains of unknown availability and was not overwritten.
