# Opt-in hybrid backend: Decimal module loops

The default is the whole-program `compiled-strict` snapshot backend.
The ordinary interpreter remains available explicitly for rollback. The opt-in `hybrid` backend lowers
eligible BSL `Для` loops to Python AST and uses Python `compile`; it does not emit
version-specific CPython opcodes. Unsupported regions execute once through the
ordinary interpreter. This is a bounded first integration, not compilation of all
BSL and not a Python/BSL security sandbox.

## Try the same program in both modes

```sh
yadinassi --execution-backend interpreter time_counters.bsl
yadinassi --execution-backend hybrid time_counters.bsl
```

These flags work with standalone BSL files, `-c`, stdin and the interactive
console. UI, database and configuration/source launch modes are not enabled by
this flag. CLI rejects incompatible launch modes. The Python API is explicit:

```python
from yadinassi import Interpreter
vm = Interpreter(execution_backend="hybrid")
vm.execute("Результат=0; Для Номер=1 По 100 Цикл Результат=Результат+Номер; КонецЦикла;")
print(vm.execution_backend_stats)  # copy: compiled, fallback, compile_seconds
```

Backend selection does not propagate to imported/source/child interpreters.
Default API construction is unchanged. Diagnostics count loop invocations, not
iterations; compile time includes successful and refused compiler preflights.

## Admission and semantic contract

The compiled subset is ordinary, standalone module execution on an exact
`Interpreter` with plain dictionary storage and proven exact Decimal slots.
Expressions: Decimal literals, names, parentheses, unary `+`/`-` and binary
`+`/`-`/`*`. Body statements: plain assignments. No closed-form loop elimination
or Python integer arithmetic substitutes for BSL Decimal arithmetic.

Bounds are evaluated once, left to right, before assigning the initial counter.
The loop rereads the mutable counter after its body. Existing numeric helpers
and the scheduler's Decimal precision/context are retained. Arithmetic failures
use the original BSL token location, and completed assignments before a failure
remain visible exactly once. Compiled execution errors NEVER trigger fallback
and replay.

The compiler checks the entire region before loop effects. Unsupported syntax,
local/reference scope, configuration/source host, database context, interpreter
family children, imports, non-standalone profiles, expression Eval, subclasses,
instance/class dispatch instrumentation, Python tracing/profiling and a replaced
runtime numeric helper all use the ordinary backend. No configuration checks,
reference write hooks or resource policies are silently skipped in those cases.

Compilation is bounded to 256 body statements, 2048 expression visits and depth
64; exceeding these limits selects normal interpretation, not partial execution.
These are optimization-admission limits, NOT new BSL execution limits. No cache
is retained, avoiding stale plans when embedders mutate AST or variable types.
Nested unsupported outer loops may interpret while eligible inner loops compile
on each invocation; repeated compilation may cost more than it saves for short
loops. There is no claim that every workload becomes faster.

No new per-iteration cancellation or resource guarantee is introduced. The
ordinary standalone synchronous For path does not have per-iteration scheduler
budget debits. Existing instrumented/subclass paths are rejected by admission.
A trusted program can still make a loop nonterminating by changing its counter.
Python execution remains in-process; this flag is not a permission boundary for
untrusted host/Python code or arbitrary mutation of runtime internals.

## Reproducible measurement

`benchmarks/hybrid_for.bsl` preserves the user's two 10,000,000-iteration loops,
timers and output/result formula. Only pasted Markdown `\*`, NBSP indentation
and the surrounding code fence were normalized. The arithmetic result must be
`149999945000000`.

```sh
python -m scripts.benchmark_hybrid_backend --backend baseline
python -m scripts.benchmark_hybrid_backend --backend hybrid
```

The harness pins the local checkout, uses explicit UTF-8, records Git identity
and runtime/backend/source hashes, validates both results and actual hybrid
admission, and emits JSON. Each invocation is a fresh process. Parsing/imports
and VM construction are outside the user's timed regions; hybrid compilation is
inside the region and is also reported separately. Use repeated alternating
runs on the same computer, not measurements from different machines.

The earlier PoC's three-pair measurement on another integration tree showed
about 12× improvement for these loops. It is not evidence for all BSL, native
1C parity or for the speed of any later source revision. No native 1C execution
was performed for this integration. User-supplied Windows/native timings must
remain explicitly separate from cloud measurements.

### Integration verification on main 20949327

After merging actual main, 87 focused tests passed in normal and `-O` modes,
including 22 hybrid tests, core/context, source-template, CLI transport and
measured source-provenance checks (313 files). Independent source/merge review
was clear. Full CI, packaged binaries and a new native 1C run are not claimed.

A fresh-process 10-million sanity pair on this exact integrated runtime produced:

| Region | Interpreter | Hybrid |
|---|---:|---:|
| Empty loop | 19.659 s | 1.644 s |
| Decimal arithmetic | 66.560 s | 5.653 s |

Both results: `149999945000000`. Hybrid compiler preflight+compile: 2.056 ms,
already inside the measured loops. This is one post-integration pair, NOT a
three-sample median. `benchmarks/hybrid-20949327.jsonl` binds both code hashes.
The preceding three pairs on the pre-merge candidate are retained separately in
`benchmarks/hybrid-38758592.jsonl`, not relabeled as results of the merged source.
Both batches used Linux x86_64 / CPython 3.12.14 on the same shared cloud host.
