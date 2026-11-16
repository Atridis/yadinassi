# Whole-program compiled backend: development status

`compiled-strict` is an explicit experimental execution backend, not a sandbox
and not a claim of full native 1C parity. The old interpreter remains an
independently selected oracle. Unsupported units raise `CompiledUnsupported`;
there is no interpreter fallback in this mode.

The compiler admits all currently executable AST node kinds. It emits Python
control flow and routes host/value operations through named semantic adapters.
Both tiers retain VM node boundaries, context policies, Decimal38 operations,
reference behavior and the existing cooperative scheduler. Counting every AST
kind is lowering-path coverage, not proof of all semantic combinations.

Each source unit is preflighted before its effects. Future dynamic Execute/Eval
and imported units can only be admitted once materialized, before *their* effects;
prior program effects are not rolled back. Known admitted AST metadata is verified,
not silently re-admitted during a call. Explicit root admission may accept a new
program version. Arbitrary Python subclasses are not automatically trusted context
adapters. Python embedding code still has Python authority.

Registries are bounded and released when the scheduler is quiescent. Pending
async work retains plans until completion or reset. Pure host-owned pending signals
can delay release, and standalone scheduler use requires a pump/reset boundary.
A resource-cap rejection is explicit and is not counted as compiled success.

## Validation and reporting

`scripts/run_compiled_tests.py --report PATH` runs existing tests under strict
policy and records emitted/helper execution, explicit rejection, old-backend use,
and cases without observed compiled execution. A caught rejection still produces
an unsuccessful strict coverage verdict. Existing explicit interpreter/hybrid tests,
CLI subprocesses, helper-only tests and negative rejection contracts require separate
classification; their assertion success is not compiled coverage. Native artifacts
and historical PoC timings do not certify this implementation.

The current broad implementation prioritizes faithful execution over speed. It
retains generator boundaries and recursive metadata guards; no scalar-PoC speedup
is claimed for it. Full existing-suite differential validation and independent
review are ongoing. Do not make this the default backend or merge on focused tests
alone.

## Host and process boundaries

UI entrypoints accept an explicit `--execution-backend compiled-strict` selection.
The first launcher argument still selects UI mode; arguments after `--` cannot
select a backend. Private catalog/form/configuration stdio children receive the
selection through argv, not a global environment variable. Each local HTTP
server captures its selected mode and enters it in every request thread. This
preserves existing request/session serialization; it does not make arbitrary
concurrent execution of one VM thread-safe. Direct host API calls from a manually
created thread outside the server need an explicit execution context in that
thread. ContextVar inheritance alone is not claimed.

The new `compiled_before`/`compiled_after` ABI belongs to strict execution.
Reference context subclasses retain their original budget/result wrappers;
the ordinary base interpreter does not acquire a new policy-hook contract or
pay for unconditional no-op hook calls. Reference instrumentation uses its
existing `_visit` embedding boundary. No absence-of-authority decision is cached.

Selecting `compiled-strict` now selects the whole-program inline pipeline, including
fresh UI/stdio subprocesses. The application-wide default remains `interpreter`
until integration gates are complete. The node-scaffold compiler is an explicit
diagnostic runner option, not a silent execution fallback. Production-style strict
execution records real block/fragment entries without detailed node counters;
coverage tests explicitly enable detailed instrumentation. Both variants retain
rejection/fallback evidence and must not conflate static inventory with execution.


## Visitor and semantic adapter extension boundaries

The reference interpreter continues to dispatch through `visit_*`, including
class/instance instrumentation and superclass visitor calls in application
contexts. The compiler dispatches through `semantic_*` adapters and never uses
legacy visitor lookup as a fallback. These adapter names were introduced with
the experimental compiler; repository inspection found no earlier adapter API.

Base visitor and adapter names initially reference the same implementation,
without an extra forwarding function/generator. They are independent attributes:
replacing `semantic_name` affects compiled execution, not implicitly the reference
interpreter's `visit_Name`; replacing `visit_Name` affects the reference interpreter,
not compiled execution. Instrument both names explicitly when both are intended.
Production contexts retain separate legacy entry implementations whose superclass
calls use `super().visit_*`; compiled adapters use `super().semantic_*`. A structural
regression test compares these bodies after normalizing only dispatch names to
prevent policy drift. No generator timing, authority, reference or error-order
relaxation is intended. Performance improvement requires a separate paired run.

## Performance acceptance plan

The user's target is the same order of magnitude as equivalent direct Python,
not a promise that host boundaries cost the same as scalar arithmetic. After the
current frozen validation and ownership change, measure fresh alternating runs on
one machine against both the untouched interpreter and direct Python. Keep raw
samples, exact source/commit/environment, preparation and execution times separate.
The Python comparison must use equivalent Decimal precision/rounding/error policy,
operation counts, mutable loop counter behavior and outputs, rather than an
optimized integer/range formula. Record unavoidable semantic differences explicitly.
Add separate module/procedure, collections, database and async cases; do not infer
those results from the scalar loop. Database comparisons must retain equivalent
transactions/receipts and effects, and async comparisons equivalent scheduling and
completion obligations. Prior timings and native-1C timings from other machines
are context only, not paired performance evidence.


### Generated-source budget and bounded helper factoring

The Python translator's AST-node threshold is only an initial inlining heuristic,
not proof that a generated unit fits its source budget. The operations checkpoint
in PR 336 has 8,428 nodes, below the 10,000-node compact-control threshold, but
its inline template emission crossed the unchanged 1 MiB cap. Disabling optional
sync segments did not make it fit. Reverting collection semantics or raising the
cap therefore does not address the size of mandatory generated Python.

Only exhaustion of generated block-template unit bytes now requests one further
lowering attempt, factoring nested blocks into generated Python helpers at depth
4 instead of 10. Ordinary units keep their existing lowering. Both attempts use
the same function, unit and operand-binding limits; registry/ownership checks
are unchanged. Unsupported semantics, integrity failures and other budgets do
not trigger this retry. If the second attempt cannot fit, admission still fails
before program effects and the engine journal restores prior registrations.
Factoring does not invoke an AST interpreter or legacy code generator.

This is a bounded engineering choice, not a claim of globally minimal factoring.
For the failing fixture, diagnostic depths 6/4/2 yielded 1,048,179 / 1,005,911 /
928,158 bytes. Depth 6 left only 397 bytes of headroom; depth 4 retained 28 prepared
sync segments. Whole-unit compact lowering used 100,854 bytes but retained no
sync segments, so it was not selected as the corrective retry. The current fix
is deliberately one extra attempt, not an unbounded search across representations.
