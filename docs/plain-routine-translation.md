# FORCE Python translation integration (Draft)

This isolated broad integration branch selects Python translation by default for
ordinary API, CLI and UI execution (`compiled-strict` with FORCE enabled). The main
branch is unchanged. Explicit `execution_backend="interpreter"` /
`--execution-backend interpreter` remains the oracle. FORCE requires owned snapshot admission and emits
Python statement/control functions and expression code; unsupported routes fail
explicitly rather than dispatching the original AST interpreter or node adapter.
Shared runtime services remain necessary for BSL values, invocation/byref, context,
forms, live authority and scheduler operations. Their use is not hidden AST execution.

## Current boundaries and evidence

Generated code includes assignments, expressions, calls/defaults, routine bodies,
If/For/While/ForEach/Try, exceptions/Return, labels/Goto, imports, Execute/Eval,
JSON/callback services, collections and Await. This is implemented scope, not a
claim of complete language parity. Generated residual functions remain for labels
and bounded nesting; fused bodies retain owned provenance metadata. Source byte,
per-function, registry and node budgets are unchanged and checked before effects.

Historical source4e675 selected cohort:510/587 tests passed,77 failed,372 passing
methods observed translation without gaps. Remaining failures include real gaps,
mutable-AST contract differences, expected strict refusals and obsolete route
assertions; they are not silently reclassified as passed. A separate919-module
inventory remains incomplete. Historical raw outcomes are retained; explicitly
legacy compiler fixtures are labelled separately and do not establish translated
coverage.

Fusion source66760 passed all60 amplified sample controls and operation counts,
with zero old adapter/interpreter-fallback counters and sealed inputs/source.
This single run is not a paired performance result. Source53d086 corrects a retained
singleton Execute identity regression;27 forced copyback tests passed afterward.
Fresh checks for the actual-main publication are reported in the PR, not inherited
from previous commits. No full-suite parity or general speedup is claimed.

Since that historical checkpoint, filtered async initialization, form argument
forwarding, and scoped dynamic Eval/Execute admission lifetime were repaired.
Transient cleanup preserves dependencies admitted by other live units; shared
metadata can conservatively remain until ordinary quiescent release. No resource
limit was raised. Ordinary-default source7b175 passed the original138-client
preflight and all60 amplified sample controls, with no old compiled node/block
functions generated and zero interpreter fallback. Those checks are not full
native parity or a speed comparison.

Large units now reuse generated expression/control code templates with immutable,
source-bound operands. Literal/name operations reuse existing owned plans rather
than allocating duplicate executable entries. Actual unique generated source,
per-function source, executable entries, owned metadata and operand bindings remain
bounded. Large units select compact generated statement functions before execution;
small units retain fusion. Both routes retain the same authority and scheduler
boundaries, with no runtime AST-kind dispatch or late compilation.

This fixes the collections scenario's admission-size refusals, but its original
20-second child still times out on the reviewed shared-template checkpoint. That
is an open execution/performance blocker, not accepted native evidence. The prior
published native run accepted five of six scenario comparisons; collections failed
before producing interpreter output. Tree comparison diagnostics are being refined
using only closed failure tokens, without exporting arbitrary exception details or
assuming that an unreproduced CI failure was a timeout. Form table receiver-specific
indexing and remaining test-contract/behavior failures are still being repaired.

This Draft is an integration/testing vehicle, not ready for production default or
merge. Light/native gates may run; heavy/full admission remains serialized with
other repository work. The older prototype sections below are historical and their
adapter behavior does not describe FORCE mode.

---

# Experimental whole-routine translation

Opt in per VM with `Interpreter(execution_backend='compiled-strict',
compiled_plain_routines=True)`. The default is false. Children with an explicit
family owner inherit this optimization selection unless explicitly overridden.
This is not an execution-backend or authority change. Shared admission/activation
refactors still run with optimization disabled; default-off is not zero code-path
change. Independent VMs and late
scheduler-created VMs without that owner do not implicitly opt in.

The initial lowering supports synchronous functions with Val parameters, exact
Decimal arguments, local assignments, ascending unit-step For loops, Return,
and addition/subtraction/multiplication. Unsupported bodies use the existing
compiled adapter, never hidden interpreter fallback. Calls, byref parameters,
objects, async and configuration runtime are not accelerated by this prototype.

Original call admission, authority checks, frame activation and cleanup remain
shared. Live tracing/profiling, hooks, unsupported scopes and values disable the
plain path before argument capture. Code generation occurs during transactional
admission; optional generated bytes count toward the existing unit budget.
Exhausting optional capacity retains the compiled adapter. Retained plans are
rechecked against current limits when admitted again. This does not grant thread
safety for concurrent use of one VM or form a sandbox against arbitrary Python.

Research baseline eeb8c8af versus candidate3aeaa4588 used eight fresh processes
in ABBA order twice, with one identical BSL caller and a 50,000-iteration Decimal
arithmetic function. Reused invocation medians were 137.32/139.92ms versus
12.69/12.66ms. Preparation was35.16 versus40.20ms. These are a narrow workload,
not whole-engine speed or full semantic parity. The Draft adds explicit opt-in
and has separate validation; those research timings are not measurements of
this later tree. Further grammar expansion requires differential tests, negative
security/budget tests, independent review and ordinary mandatory gates.

## Broad integration branch checkpoint

The integration branch additionally explores scalar strings/booleans/Undefined,
Var, comparisons and short-circuit expressions, If/While/Break/Continue, Val
procedures/default-bound parameters, and explicit mixed continuations. Unsupported
operations remain existing compiled adapters. Pure prefix transfer and resumed
segments have separate route counters; they are not whole-routine coverage.
Resume reads current live storage only after bounded ABI/context/provenance/type
validation, with no replay of completed opaque effects or late compilation.

Source939e7b4ac passed a567-test selected regression batch (including negative
cases). Aggregate route observations were53 whole-plain calls,13 resumed segment
entries,24 suffix entries and1307 adapter blocks, with zero interpreter fallback.
These aggregate counts are not per-case coverage or a full-suite parity verdict.
Earlier source8a6 passed all60 controls from the amplified sample but observed zero
resumed segments and30 type denials; no speed benefit for resumption is claimed
from that sample. Raw failures, including a corrected no-op Var codegen defect,
remain separate source-bound evidence. Module-entry translation is a separate
prototype and is not part of this checkpoint. Default selection remains unchanged.
