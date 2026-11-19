# Direct-only runtime retirement, first slice

The only product execution backend is `python-direct`. Explicit `interpreter`,
`hybrid`, and `compiled-strict` selections are rejected by Interpreter and the
shared UI execution policy. The CLI no longer exposes `--legacy`. Unsupported
language features report their actual diagnostic, not advice to select a retired
engine.

Physically removed: compiled_backend, compiled_inline, compiled_roles,
hybrid_backend, plain_modules, plain_routines and all python_translation_* modules.
The runtime's old whole-module scheduler dispatch, tree visitor dispatch, generic
call/routine evaluator, expression Eval/Execute evaluator and compiler factory
bodies are removed. Retained historical entrypoint names reject explicitly; they
are not fallback routes. Public execute/execute_program compile directly.

## Deliberately remaining work

This is not a claim that every historical execution-related definition is gone.
Runtime still contains semantic helpers and individual visit methods, async body
and activation helpers, callback machinery, module import helpers and the shared
Scheduler/ExecutionContext. Direct source/ownership adapters consume parts of
these types, field layouts and definition-time ABIs. Owning interpreter subclasses
also retain historical compiled branches. These require a separate dependency
migration; the removed product backend cannot select them.

The isolated native_bare compiler is unchanged. Parser, AST model, control-flow
validation, canonical values, and authority helpers are retained.

Old engine tests/benchmark lanes and native comparison drivers that explicitly
select retired backends are not migrated by this slice. Ordinary CI/full-suite
success is NOT claimed. New focused tests prove physical engine-module absence,
backend rejection, direct execute/prepared/AST execution, and fail-closed old
entrypoints. Twelve focused tests pass in normal and optimized Python.
