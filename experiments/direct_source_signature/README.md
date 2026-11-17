# Source checkpoint signature comparison

Baseline 5ce477bb. Seven alternating fresh-process pairs; three complete starts
per case. Startup still compiles the module and checks every routine at every
checkpoint. SourceApplication construction is outside the timer. Both workloads
sum 1000 increments and emit the same checked BSL numeric presentation.

| Additional routines | Before median ms | After median ms | Improved pairs |
|---|---:|---:|---:|
| 0 (control) | 52.55 | 47.87 | 6/7 |
| 100 | 294.39 | 193.86 | 7/7 |

Only temporary signature allocation and redundant parameter iteration are removed.
No purity assumption, admission cache, version token, skipped routine scan or
weakened checkpoint is introduced. Every mutable field still receives canonical
type checking, even when an earlier field or parameter count differs. Registry
identity and module layout checks remain unchanged.

Tests cover each mutable signature field, missing/extra/invalid parameters, and
malformed parameters following an earlier mismatch. Malformed AST with several
simultaneous corruptions may fail closed earlier with BoundaryViolation instead
of AttributeError; no malformed declaration is admitted.

The first benchmark invocation stopped before collecting samples because the
harness expected an ungrouped integer string. Its expectation was corrected to
the unchanged BSL `1\u00a0000` output before the complete run recorded here.
No production output, source fixture or comparison semantics were changed.
