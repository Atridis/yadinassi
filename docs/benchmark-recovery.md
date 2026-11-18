# Performance report recovery scaffold

This is **not** a replacement performance job or a measured report. It recovers
identifiers and report dimensions from surviving reports, not executable sources.
No old timings, ratios or counters are copied into new measurements.

## Evidence

`scripts/benchmark_recovery_manifest.json` records SHA-256 of three surviving
reports. `native-bare-8666e8-checked-report.md` has 11 core and 34 method cases.
`github-summary.md` adds seven Structure methods, producing 41 method cases.
`native-pairs-912b2b-report.md` supplies later Map iteration context, not new IDs.
These reports cannot establish equality of a reconstructed workload's source.

N=512 and N=4096 are required for all identifiers. Four layers are distinct:
Python, classes, ordinary BSL API (preparsed AST, compilation included), prepared
BSL API (plan prepared before timing). The sole deliberate historical skip is
`method.valuetable.find` at N4096 in all layers. Do not silently omit that row.
The 416-row grid contains 208 BSL case/size/API entries and matching baseline
layers; currently 412 unbound rows and four explicit skips. Missing is not zero.

## Runtime binding contract

The recovery base is 6d2df16. Its four-case smoke covers array.add and collection
build/scan, but does not restore the historical full method workload definitions.
Current bare APIs are `Interpreter.prepare(source)`, `execute_prepared(plan)` and
`execute_program(preparsed_ast)`. Bind each case only after verifying source,
operation count, arguments, result and full mutable state for all four layers.
Use fresh fixtures/reset outside timing. Unsupported behavior must be reported,
not converted to a measurement or routed to legacy code. Never infer binding
availability merely from the historical case ID or a passing unrelated smoke.

Each future measured row needs current git/tree/dirty provenance, BSL and Python
workload hashes, exact operation semantics, environment, raw wall and CPU samples,
round/batch sizes, validation evidence, and separately profiled call counts.
Compare equal int-based workloads; do not reuse old Decimal-based core scripts
as though they were the recovered int series. Map iteration differences (Python
values versus BSL key/value pairs) must remain visible.

`benchmark_call_counts.capture` counts current-thread Python `call` and C
`c_call` events separately, once each (not returns/exceptions). It includes the
workload wrapper call, excludes its own profiler shutdown, rejects an existing
profiler and restores profiling after errors. It is **not a timer**, not an
allocation counter and not a count of work done inside C. Run diagnostics in a
separate untimed pass/process after unprofiled timing, then validate outside the
profiled region. It does not claim byte-for-byte historical counting equivalence.

## Integration still pending

Reuse `benchmark_report.py`/`benchmark_summary.py` terminology, single ratio
legend, and paired tables once real adapters exist. Existing diagnostic and
extended scripts are not drop-in 41+11 bare runners. No CI workflow is changed
by this scaffold. A future CI runner must preserve partial artifacts on error and
fail coverage validation when an expected measured row is absent; it must not
make this scaffold's successful generation count as a passing benchmark.

Generate the explicit coverage artifact (no runtime imports or execution):

```sh
python scripts/benchmark_recovery.py --commit "$(git rev-parse HEAD)" --output /tmp/recovered-coverage
python -m unittest tests.test_benchmark_recovery
python -O -m unittest tests.test_benchmark_recovery
```

## First runnable recovery slice

`benchmark_recovered_drivers.py` binds six reconstructed workloads: assignment,
addition, string.length, Array.Add, ValueTable.Add and ValueList.Add. Its source
strings are emitted in JSON (Python baseline and BSL included). These are explicit
new contracts, not proven source-identical historical implementations. Collection
fixtures are created outside timers; Add measures only N additions. Table.Add
adds default rows to an existing one-column table; ValueList.Add fills all four
default fields. Validation checks full ordered state and table schema/row owner.

Run `python scripts/benchmark_recovered_drivers.py --output /tmp/recovery-run.json`.
The command measures N512/N4096, alternating layer order, five rounds by default,
with unprofiled wall/CPU medians, then a separate untimed profiler pass. Both BSL
APIs operate on the same parsed source; only ordinary API compilation is timed.
Unsupported/unbound cases remain explicit. Any bound-case error fails the command
and remains recorded; coverage remains incomplete. No workflow is activated.

## Isolated backend revision

The runnable driver now targets isolated base `3b73b2c8`, explicitly calling
`native_bare_compiler.prepare_module/execute/execute_prepared`. **It does not
measure or change the public default backend.** Its `default` layer key means
explicit bare execution including compilation of preparsed AST, not public
`Interpreter.execute_program`. The JSON records this distinction and compiler
hash. The earlier six-case public-call description applies only to the prior
recovery checkout, not this isolated runner. A seventh reconstructed case,
Map.Insert, verifies all integer keys/values with no entry-allocation scan inside
the measured operation. Public dispatch isolation is regression-tested.

The current bound subset is 18 cases (3 core, 15 method). The compact sample in
`benchmark-recovery-sample.md` was generated from exact clean `8a6b8edf`, five
rounds at both required sizes. It is preliminary and includes explicit uncovered
IDs. Full raw samples and source bodies are emitted by the runner, not embedded
in this documentation. Map.Iterate uses the same `dict.items` + both key/value
projections in Python and classes; BSL lowers its entry projections directly.
The input Map is prefilled outside timing (unknown receiver, iterator choice once
before the loop); this is not a benchmark of construction or entry allocation.
Read-only workloads additionally validate the complete original collection state.

## Next recovery slice (31 bound identifiers)

The additional 13 drivers are all remaining Array methods, all seven Structure
methods, and core calls/byref. They define **new explicit contracts**, not inferred
historical source equivalence. Array.Find performs N successful ascending searches
(quadratic total work); Insert prepends N times; Delete computes descending indices.
Structure.Insert overwrites one fixed name after its first insertion; Delete
removes one name then performs N-1 missing deletes. Neither claims to measure N
distinct field operations. Structure iteration uses N prefilled fields, with Python
values versus classes' lightweight entry objects. Calls defines a value-argument
function in each timed call; byref uses an explicit mutable cell in Python and a
BSL procedure incrementing its actual argument. Fixture creation and validation
remain outside timing; both compilation-included and preprepared bare paths are
checked. All raw workload sources and their hashes remain in the JSON.
