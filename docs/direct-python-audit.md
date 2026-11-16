# Direct Python execution: audit-driven broad slice (Draft, incompatible)

The supplied `perf_audit1.md` inspected research source `5c9157ed`. Its exact
benchmark harness/raw samples were not supplied, so the numbers are not treated
as independently reproduced measurements. Source inspection confirms the seven
mechanisms, with two qualifications: the tiny-routine threshold exempts loops;
expression depth can outline a synchronous expression rather than always call
an evaluator.

## The substantial change

`live_module_state` executes against the caller's **same native dict**. Reads
are inline dict.get/sentinel expressions; writes are native subscriptions.
There is no Interpreter.set_variable adapter, VM dispatcher, per-access lease,
module-state copy, or final flush. Generated functions and private locals remain
ordinary Python. References retain the same dictionary/key and aliases.

Without the explicitly selected `authority_checkpoints` repair, local source
calls do not acquire context checks at the call, function entry and function
exit. Explicit external services keep their own binding/effect boundaries.
Trusted local execution also excludes artificial allocation quotas. It does
not promise custom cancellation polling within pure loops; normal Python
interrupts remain available.

```python
from yadinassi.experimental_naked_collections import prepare, REPAIRS
from yadinassi.experimental_naked_boundaries import BoundaryContext
state = {}
program = prepare(source, repairs=REPAIRS - {'resource_bounds', 'authority_checkpoints'})
program.run(state, context=BoundaryContext(services=services))
```

The environment opt-in remains required. This is the standalone direct route,
not a claim of ConfigurationApplication/NoContext/server capabilities. The old
universal scope adapter was not included: its approximately 11x module-loop
regression is not acceptable as the goal of this work.

## Audit disposition

1. **Repeated ClosedLease scans:** present in production's old specialized path.
   The direct standalone path does not use ClosedLease/ABI/world scans at all.
   No monkeypatch-safe or shared-host isolation guarantee is claimed for it.
2. **Local calls:** generated Python functions, positional actuals and return,
   rather than call_routine/context activation/_Return in the direct path.
3. **Byref:** retained direct references/lexical cells and dictionary slots;
   no exclusion of all byref routines. Incoming canonical Reference is preserved;
   noncanonical Python subclasses are not treated as privileged references.
4. **Collections:** direct native list/dict operations and narrow concrete
   semantic helpers, not CollectionRegion.bind/invoke/call or graph repacking.
5. **Node protocol/statistics:** direct path has no general per-node VM protocol.
   Separately, production block/leaf detailed kind dictionaries now honor
   DETAILED_INLINE_STATS. Admission checks remain unchanged. A stable speedup
   from this statistics-only patch was not established.
6. **Locks:** trusted direct loops need no checkpoint. An optional explicit
   SingleOwner context provides cancellable exact-header-budget execution without
   a per-checkpoint lock. Shared concurrent-budget mode is separate and unchanged.
7. **Residual dynamic work:** live module reads no longer use locals(); source
   namespaces/calls are compiler selected. Dynamic host signatures stay live per
   argument. Full type propagation and further helper elimination remain work.

## Evidence and honest limits

`experiments/naked_translation/business` contains self-contained invoice and
cyclic-graph workloads, output/alias/full-event controls, cold setup+execution and
warm execution samples. These are synthetic business workloads, NOT complete
product applications, native-1C runs or security equivalence. Three rotating
fresh-process trials per backend, three warm runs per process are exploratory,
not a universal performance guarantee. Warm runs reuse their module state.

Preparation of the six existing integration files succeeds only for dates and
numbers; neither was executed by that coverage probe. Collections stops at
FixedStructure; functions/strings/values stop at Execute. This is **2/6 prepared,
0/6 verified executions**, not broad compatibility. New incompatibilities and
red integration tests may remain visible in this Draft rather than blocking the
whole direct transition.

Known missing/changed contracts: configuration/import/system namespaces; exact
NoContext AST metering; admission/generated/retained-source budgets and ownership
lifecycle; persistent routine registry across separately prepared source modules;
conditional Var shadowing; arbitrary host monkeypatch semantics. Preexisting
module globals can be declared through prepare(module_names=...). Caller keys
must already be casefolded strings. The direct path is not a sandbox. Do not
silently apply it to a restricted/shared-host service or conceal data corruption
and security failures as harmless compatibility differences.

The associative serialization package is an independent production-semantic
change in this PR: associative order is not contractual, typed contents and
roundtrip remain checked. This research PR remains Draft; #336 is unchanged.
