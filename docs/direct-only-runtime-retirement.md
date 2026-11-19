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
After the second slice, individual tree-walk visit methods and the old async
routine body/invocation activation executor are physically removed too. Runtime
still contains semantic helpers, callback machinery, module import helpers and the shared
Scheduler/ExecutionContext. Direct source/ownership adapters consume parts of
these types, field layouts and definition-time ABIs. The product adapter
checkpoint below removes the retired arms from its owning entrypoints.

The isolated native_bare compiler is unchanged. Parser, AST model, control-flow
validation, canonical values, and authority helpers are retained.

Old engine tests/benchmark lanes and native comparison drivers that explicitly
select retired backends are not migrated by this slice. Ordinary CI/full-suite
success is NOT claimed. New focused tests prove physical engine-module absence,
backend rejection, direct execute/prepared/AST execution, and fail-closed old
entrypoints. Twelve focused tests pass in normal and optimized Python.

Second-slice validation: 13 focused tests pass normal/-O. A broader imports,
prepared and source cohort runs 58 tests with one expected obsolete test setup
error: it explicitly constructs compiled-strict. This assertion is not weakened
or silently skipped; remaining 57 tests pass. No full-suite claim.

## Product adapter checkpoint

The form event, source form, document posting, catalog preparation, form session
and configuration application adapters now call their direct entrypoints without
retaining a second scheduler/tree-walk execution arm. Single-node adapter entry
names explicitly reject; budget/ownership hooks used by direct compilation remain.
Form sessions without prepared direct handlers fail rather than constructing an
old activation. Unconnected configuration session initialization remains an
explicit error, including its pre-existing caller authorization.

No source metadata, safe-mode execution, ownership checks, transaction checks,
revoke checks or direct compiler changes are introduced by this checkpoint.
This does not migrate unrelated semantic helper methods or enable unsupported
session initialization. Three new focused tests cover explicit errors and absence
of old dispatch; existing owning/form/configuration/NoContext tests cover the
actual direct lanes. Full Light/legacy-test compatibility is not claimed.

## Test cleanup checkpoint

Removed five modules tied to deleted implementation APIs: compiled_code_cache
(7 methods), prepared_routine_metadata (8), owned_lookup_once (6),
python_call_site_metadata (3), python_template_source_binding (3). These tested
retired code-cache statistics/limits, engine-owned layouts/version registries,
expression call-site metadata and generated-source operand binding. Their engine
assertions are retired, not counted as direct passes. Two portable contracts from
the cache module survive in test_direct_runtime_isolation_diagnostics: callback
isolation/collection and source-location diagnostics.

Form argument tests now exercise direct execution with their functional assertions
unchanged. Four pass; the configuration NoContext sequence still fails explicitly
because direct handlers require synchronous module-context routines. The native
ColumnsClear profile imports its measurement helper only in the two cases using
it: 18 other provenance/contract tests run, while those two report the unresolved
removed-translator import as errors. No skip, expectedFailure or partition change.

On the e91a700 base, discovery changes from 16,873 IDs / 61 import placeholders to
16,893 IDs / 54 placeholders. Seven placeholders disappear: five retired modules
and two restored modules; 27 real cases become collectable. Focused normal/-O:
27 tests, 24 passes, one failure and two errors in each mode. This is exposed
remaining migration work, not a green-suite claim.
