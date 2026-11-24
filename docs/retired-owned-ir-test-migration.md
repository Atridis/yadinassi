# Retired owned-IR test coverage migration

Scope: `test_owned_context_guards.py` and `test_owned_ir_experiment.py`.
The old subprocess launcher imported deleted `compiled_backend.Engine`, so import
collection alone did not reveal its failures. No production code changes here.
The direct compiler is the only selected backend. Unsupported live behavior is
still a failing test, never an expected failure, skip or fallback.

## Retained behavior

| Old concern | Current executable coverage |
| --- | --- |
| Event/object budgets | `test_event_and_object_guards_preserve_real_execution_budgets`: scalar form source cap, specialized adapter-only entry, and real catalog preparation expansion; managed form execution budget remains a separate live test |
| Constant/posting live references | Actual constant handler byref storage, native posting outcomes, Boolean cancellation and same-owner query scenarios; no synthetic legacy `argument()` generator |
| Configuration declaration/import authority | Original declaration identity allowed, unrelated same-name declaration and file import denied |
| Foreign AST classes | Direct source-AST preflight must reject before `Touch` or assignment |
| RHS/actual/block/handler mutation | Direct probes retain original effects and final-value assertions, without Engine stats |
| Opaque host callbacks and dual metadata | Original expectations retained as ordinary failures if unsupported; no claim these modes are implemented |
| Module exports, readiness and revocation | Real loader tests for namespace/family rebind, retained exported callable lifetime, late layout change before effects. Removed synthetic `_Module` injection, which bypassed today's loader |
| JSON/completion metadata | Real imported source replaces synthetic module injection; rewriting its file after loading must not replace the active callback contract. Missing callback support fails visibly |
| Configuration/form product behavior | Original configuration callbacks, constant manager and form error-state fixtures rerun explicitly direct |
| Forged reuse view | Original AST accepted; unrelated AST and spoofed origin object denied by both live reuse adapters |
| Existing host AST setter | Direct compilation must not replace the caller's custom setter |

Subprocess runtime imports inherit parent `-O`; probe assertions are compiled
with `optimize=0` so optimized test runs cannot accidentally erase the oracle.

## Deleted implementation-only matrix

The following depend on the removed Engine/owned execution representation rather
than an available product entrypoint: per-engine FULL/OFF flags; origin monitors
and active-ancestor scans; private owned node/list registration and fingerprints;
Engine journals, memoization, registry traversal and release; inline-IR cache,
generated-unit limits and Engine collection budgets; cross-engine owned views and
origin backlinks; automatic immutable AST guards; old mutable-vs-snapshot mode
comparisons. There is deliberately no replacement claim for those internal
mechanisms. Their product-facing mutation/authority expectations are retained
above where independently expressible.

The FULL-monitor wrapper over the former codegen/lifecycle/ABI suites was removed:
live parts already run in `test_compiled*`; deleted policy-ABI and metadata Engine
classes cannot be rerun. The duplicate OFF snapshot-mode probe is covered by the
retained direct target/block mutation probes. Quiescent Goto mode comparison was
retired with mode selection; live Goto/error and routine replacement expectations
remain in `test_compiled_codegen` and `test_compiled_snapshot_contract`, including
their current failures.
