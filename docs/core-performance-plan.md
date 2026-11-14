# Core BSL execution performance: planned language track (2026-11-14)

## Evidence and limits
Read all 204 lines of the user's pasted message. User Windows 10M iterations: empty29.273s vs native1C2.720s (10.76x), arithmetic111.950s vs8.024s (13.95x), same149999945000000. Versions/hardware/build flags are not recorded. Pasted macOS/prototype results are not verified here and must not be promised as production gains.

Inspected main387585929afa345e98bc1901993620835441106c and combined prepared-plan/M2/import-cache preview136de2f2060ce6f85021ddc8a2d523b996564bdf. No runtime/PR/workflow changes. language_next was completed; other ongoing work remains undisturbed. Local preview source tree4147dfe27425dffa59f09c1014b1bb2f1ea51288 is published equivalently as43403c19fc1758d925e7ee31f6012d8a03e94a48.

Fresh exploratory Linux x86_64 CPython3.12.14:100k iterations, one warmup+3 measured executions, parse and VM construction excluded. Execution includes normal program validation/scheduler boundaries. Fresh VM each repetition, same parsed AST. Result assertions for all8 cases passed. Decimal context outside execution28; scheduler explicitly enters38-digit context (async_runtime.py238–239). Not comparable to user Windows time and not a performance acceptance gate: shared host, short sequential samples.

Median seconds (main / combined preview):
- module empty .1925/.1881; assign .3199/.3358; add .4732/.4799; arithmetic .6553/.6621
- routine empty .2068/.2685; assign .3745/.5080; add .5579/.6371; arithmetic .7513/.8344

This does NOT establish isolated M3 regression: multiple changes, sequential noisy runs. It does establish that existing work must not be advertised as solving this benchmark. Repeat randomized paired isolated revisions before attribution.

Separate cProfile10k combined: module arithmetic940481calls,80005 _visit,40001visit_Name,100004locals,60004casefold; routine arithmetic1270881calls and10006/10003 PreparedBlock.matches calls. These counts support dispatch/context overhead hypotheses. No optimized variant was benchmarked.

Code anchors (combined): runtime.py866block,895_visit,919visit_Name,1027visit_Binary,2216set_variable,2433iteration,2442visit_For; syntax/parser.py632PreparedBlock.matches. For still constructs ast.Name twice/iteration and Decimal(1), block still runs for empty body. M3 caches control-flow plans only and validates mutable AST; it is NOT expression lowering or constant-time cache validity. M2 only narrows constant call dispatch. Import-cache targets attribute calls, absent from this benchmark's loop body.

## Ordered backlog, after current language checkpoint, without interruption

P0: commit reproducible benchmark + semantics contract, no runtime changes.
- Keep exact user10M BSL fixture (output outside timing) plus empty/assign/add/composite module/routine microbenchmarks. Save normalized fixture (markdown escaping is not BSL).
- Capture exact SHA/tree, dependency lock, Python/compiler/PyInstaller mode, OS/CPU, native1C version/mode, compilation profile, seeds/N, raw timings, outputs, warmup policy.
- Compare paired alternating baseline/candidate in fresh processes on same host, 5–7 measured repeats, cold/warm separately. Parse/load and execution reported separately; packaged exe vs source separate. Profile in separate runs, never use profile times as speedup evidence.
- Full10M validation on Windows alongside user's native1C; bounded100k smoke for CI, larger benchmark opt-in and not flaky hard wall-clock assertions.

P1: low-risk For allocation cleanup; independently review/test.
- Hoist immutable Decimal step and Name descriptor per loop activation; preserve dynamic self.visit_Name/self.set_variable hooks and reread counter after body. Do NOT use Python range, unroll, closed-form sums, or freeze a local slot across awaits/callbacks.
- Empty-body shortcut only if it preserves subclass iteration/block hooks, lifecycle/budgets and can prove body immutability. Otherwise leave it for later.
- Normalized-name helper only with explicit hook contract; caching mutable resolved values/authorization/context forbidden.
- Require measured gain beyond noise, no regression in arithmetic/routine paths. Do not promise closing14x gap from this task.

P2: prepared execution representation proposal + prototype behind explicit opt-in.
- Build on existing M3 rather than duplicate cache: normalized identifiers/operator tags/statement plans with source coordinates and original AST ownership.
- Preserve mutable-AST validation, including node type changes; current test_goto.py mutable routine rejection BEFORE argument side effects is mandatory. Do not remove matches merely for speed. Decide immutable lowered snapshot vs instrumented versioned AST deliberately; external execute_program mutable AST needs fallback/revalidation.
- Cached dispatch must honor Interpreter subclasses/overrides. No base-class method bypass for form/posting adapters.
- Profile M3 matches/find overhead independently and scope plan lookup to validated activation with defined invalidation, not undocumented validate-once.

P3: synchronous expression lowering, only after P0/P2 contracts.
- Target Literal/Name/Binary/Assign first; retain Decimal38, evaluation order, boolean short-circuit, dynamic types/coercions and original error coordinates.
- No assumption first-iteration Decimal remains Decimal. Exact supported node/type guards; unsupported/mutable/async behavior takes semantically equivalent slow path, without re-evaluating side effects.
- Separate execution-step accounting/error wrapping from generator plumbing so fast nodes consume same semantic budget units. Form/posting/source-host hooks and host-failure identity preserved. Budget errors must remain uncatchable where specified.
- No speculative reassociation (a+i*3-7), float/int substitution, native-code eval, or result-based loop elision.

P4: integration/acceptance.
- Differential old/new randomized tests and exact native1C fixtures for numeric/control-flow edge semantics; async suspend/resume/error tests; all focused then full required CI sequentially on exact head/base.
- Host1C timing is separate from proof of semantics. No native parity claim from Python benchmark or browser smoke.
- Report actual speed distributions and memory/startup costs; broader bytecode VM only if remaining profiles justify complexity, not prerequisite for initial allocation cleanup.

## Semantic regression matrix (must exist before optimized dispatch)
- Decimal fractions/38-digit rounding/overflow/division, mixed string/date/bool operators, errors/source line-column, order and short-circuit.
- For fractional/descending-empty bounds; each bound evaluated once and in order; mutable counter in body, ref parameter aliases, module vs routine shadowing, postloop counter, break/continue, nested/outward goto, try/finally-equivalent cleanup.
- Runtime subclass visit_Name/set_variable/_visit/iteration/block hooks; form fields/read-only/configuration assignment authorization; references cannot become snapshots.
- Async calls/await inside bounds/body/expression, scheduler context switching and cancellation, callback reentrancy. Never retain frame-local storage across yield without validated identity.
- Mutable AST before execution, before routine arguments, nested body/class/label mutation, dynamic Execute/Eval. No stale planned control flow.
- Form and posting execution budgets, host failure identity, transaction admission/rollback, recursive limits. Explicitly examine existing empty-loop budget gap separately: current _visit accounting does not itself charge every empty-loop iteration; do not silently make it worse or claim it already has per-iteration coverage.

## Reproduce local measurements
Use dependency-complete Python (current shared venv /tmp/track320-venv/bin/python); no install needed.
`python benchmark.py --repo CHECKOUT --iterations 100000 --repeats 3 > baseline.json`
`python benchmark.py --repo CHECKOUT --iterations 10000 --repeats 1 --profile > profile.json`
Raw JSON/pstats are alongside this plan. This is a research harness, not yet checked in or a full CI result. For archives without .git pass --git-repo SOURCE_REPO --revision EXACT_SHA; ensure archive matches that revision.

## P0/P1 implementation checkpoint

The checked-in harness is `benchmarks/for_loop.py`. Example:

```sh
python benchmarks/for_loop.py --repo CANDIDATE --baseline BASELINE --iterations 100000 --repeats 5 > paired.json
```

All eight module/routine cases use fresh subprocesses with alternating paired
revision order, one warmup and one measured execution per sample. JSON preserves
raw measurements, result checks, parse time, revision/tree/dirty state, Python,
platform and installed dependency versions. It does not infer a native version
or compare source execution with packaged binaries. Use `--iterations 10000000`
for the user-sized workload; arithmetic must produce `149999945000000`.
Do not edit either checkout during a measurement run. No wall-clock test gates.

The first runtime slice hoists Decimal(1) and reuses only the internal For counter
syntax descriptor on the exact base Interpreter with its original Name handler.
Every read still dispatches through self.visit_Name, every write through
self.set_variable, and the counter is reread after the body. Per-read guards
notice class/instance hooks installed during callbacks; subclasses retain fresh
Name descriptors. No body elision, local-variable/value caching, bound-method
caching or altered budget accounting is introduced. Existing empty-loop _visit
accounting remains For + bounds, not one charge per iteration. Fixing that gap
would be a separately reviewed semantic change, not hidden in this speedup.

### Measured P1 result, not native parity

Raw paired data: `benchmarks/results/for-allocation-linux-20261114.json`.
Clean candidate7377f579 vs clean baseline5db8aa70, source Linux CPython3.12.14,
100000 iterations, 7 paired repeats, fresh process each sample, one warmup.
No profiler. Source execution only, no Windows/packaged/native1C comparison.
Medians in seconds (baseline → candidate; ratio of medians):

| Scope | Empty | Assignment | Addition | Arithmetic |
|---|---|---|---|---|
| module | .1863 → .1631 (1.142×) | .3376 → .3067 (1.101×) | .4693 → .4437 (1.058×) | .6943 → .6579 (1.055×) |
| routine | .2711 → .2336 (1.161×) | .5219 → .5017 (1.040×) | .6543 → .6258 (1.046×) | .8256 → .8191 (1.008×) |

Empty cases improved in all7 paired samples; routine arithmetic distributions
overlap substantially and do not establish a meaningful gain. This narrow
allocation change does not close the user's reported10–14× native gap. Large
remaining costs include expression dispatch and routine plan validation; next
work must target those with differential semantics, not promise these ratios
for10M or another machine. The full10M run is separate opt-in work, not covered
by this100k measurement. No native parity or full required CI claimed.
