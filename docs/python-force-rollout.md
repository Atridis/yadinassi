# Research: whole-program Python translation campaign

This branch is isolated research, not a change to the default backend and not a
full-parity or performance verdict. `Engine.FORCE_PYTHON_TRANSLATION = True` is a
test-only fail-closed switch. Use it with an explicitly constructed
`Interpreter(execution_backend='compiled-strict', compiled_plain_routines=True)`.
Unsupported generated execution raises rather than falling back to an AST adapter
or the interpreter. The interpreter remains a separate oracle.

Generated functions now handle module/routine blocks, control flow, calls,
references, collection/property operations, asynchronous suspension and admitted
dynamic units. Live runtime services still perform security, context, source,
argument-order, invocation and resource checks. Metadata AST identities remain
for provenance and diagnostics. Generated functions currently use the scheduler's
generator protocol; this is not a claim of fused straight-line execution or of
CPython-equivalent speed. Fusion is a separate measured iteration.

## Source-bound evidence

A fixed 587-method selected regression cohort was run under a constructor harness
that forces implicit root VMs, while keeping explicitly requested interpreter
VMs as oracles. Unobserved and expected-rejection passes are recorded separately.
The original raw failures and implementation-specific assertions were preserved.

| Source | Failed methods | Passed methods | Positive pass with observed translated route and no gap |
| --- | ---: | ---: | ---: |
| `35ad80727` | 411 | 176 | 6 |
| `f7dfb976e` | 218 | 369 | 228 |
| `fb1ef1232` | 95 | 492 | 352 |
| `4e675252a` | 77 | 510 | 372 |

These are not percentages of the language or of the complete test suite. The
remaining failures include real issues, obsolete implementation-counter
expectations, explicit mutable-AST contract tests and expected forced-budget
rejections. No failing test was silently relabelled as a pass.

The owner's 60-control amplified workload passed on `4e675252a`, with matching
IDs, operations and controls and no AST-adapter or interpreter fallback observed.
Its old harness inline counter was explicitly replaced in memory by the new
translation-entry witness; functional checks were unchanged. That single smoke
run is not a paired speed benchmark.

A separate resumable inventory covers 919 existing test modules on frozen
`4e675252a`, with source/harness hashes, bounded subprocesses and explicit
unsupported/error/timeout/route records. Completion is not a PASS verdict.

After that source, repeated synthetic block admission was corrected to reuse
owned identities (`ea21cd6ca`), with a ten-reprepare registry-size regression.
Retention uses shared pruned namespaces, preserves admitted routine/default code,
and conservatively retains source-byte charges. No source/function budget was
raised. Further failures discovered by the large inventory remain open work.

No Ready/full/merge decision follows from this checkpoint. Mandatory repository
review and CI gates remain separate.
