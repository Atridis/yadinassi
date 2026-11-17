# Three execution layers, without a performance gate

Run from the repository root with its supported Python environment:

```sh
python -m unittest tests.test_benchmark_execution_layers
python scripts/benchmark_execution_layers.py --iterations 1000 --rounds 9 > layers-default.json
YADINASSI_UNSAFE_COLLECTION_ABLATION=1 python scripts/benchmark_execution_layers.py \
  --bsl-route experimental --iterations 1000 --rounds 9 > layers-experimental.json
```

The second command measures the public `Interpreter()` default, currently
`python-direct`, without an explicit backend override. To compare the legacy
backend, add `--bsl-route compiled-strict` and save a separate report. The JSON
records both the requested route and the actual backend.
The third explicitly measures the **trusted, standalone research translator**,
not the production VM or a configuration application. It retains the research
semantic repairs but excludes optional `resource_bounds` and
`authority_checkpoints`; the exact repair set is recorded in every case. It is
not safe to use this opt-in as an untrusted-code execution service.

Use `--case arithmetic` (repeatable) to select workloads. Iterations must be
1..100000. At least three rounds are required; use nine or more for evidence.
Run serially on an otherwise idle machine, preferably repeat the entire command
in fresh processes. Never compare numbers from different machines as a backend
speedup. There is no pass/fail timing threshold.

## What is compared

Each workload has three hand-written, result-equivalent implementations:

| Workload | Native Python | Python using yadinassi | BSL |
|---|---|---|---|
| arithmetic | Decimal operators | `binary_values` operators | arithmetic loop |
| calls | local Python value function | `HostFunction` plus numeric operators | source `Function`, `Val` argument |
| byref | explicit mutable one-slot cell | `Reference` and reference-declared `HostFunction` | default by-reference source procedure |
| array | `list.append` and index reads | `BSLArray.add/get` and numeric operators | `Array.Add` and index reads |
| map | numeric-key `dict` insert/get | `BSLMap.insert/get` and numeric operators | `Map.Insert/Get` |

There is no yadinassi scalar-number wrapper class: BSL numbers are `Decimal`.
Therefore the classes column uses the actual numeric operator helper rather than
inventing a proxy. All three columns use Decimal values and exact bounded integer
arithmetic; the native column is not quietly using faster floats or ints for the
workload's data. Python loop control uses `range`; BSL loop control uses its actual
backend implementation. Numeric indices are converted according to the API.

This is **equivalence on these workloads**, not general Python/BSL parity.
Maps use only unique Decimal keys, no Boolean/number collisions or object keys;
arrays have valid nonnegative indices. No locale-sensitive strings, division,
exception conversion, concurrency, authorization changes or native-platform
integration are measured. Python byref is modeled explicitly because Python has
no BSL-style rebinding of a caller variable. Direct `HostFunction.__call__` and
collection methods do not include the VM's argument binding/member dispatcher;
source routines do. The classes column is not a complete alternative BSL engine,
and differences cannot all be attributed to class allocation alone.

## Measurement boundaries

* Factory construction and BSL parse/prepare are reported separately. The small
  Python workload factory creates both Python closures, so its time is shared,
  not falsely allocated to individual layers.
* The first invocation is recorded separately for **every** layer. Default and legacy
  BSL use public `execute_program(preparsed_ast)`: lazy compile/registration on
  first entry belongs to `first_execution_seconds`, not reported parse time.
* One additional warmup is excluded. Steady execution still includes public
  module-entry validation, source-routine registration, backend cache checks and
  scheduler work. It is deliberately **not** an internal guard-bypassing runner.
  Research BSL uses the separately prepared program's `run({}, context=...)` API with a fresh module dict each time.
  Default and legacy reuse one VM and its scope/cache; source statements overwrite all
  measured variables and allocate fresh collections. This retained-scope vs fresh
  dictionary difference is part of the routes, not hidden setup equivalence.
* Every invocation resets its own workload state. Collection construction,
  insertion, function/reference creation and traversal are work, hence timed.
  Data generation is not precomputed only for Python. Imports are outside the
  per-case setup timer. There is no output formatting inside execution timing.
* All results are validated outside execution timing against an independent
  closed-form expected Decimal, including first and warmup calls. Wrong type or
  value aborts the report. There are no acceptable faster-but-wrong samples.
* Round order rotates Python/classes/BSL to spread first/last-position bias.
  Raw wall and process-CPU samples, median, min/max and median absolute deviation
  are retained. Ratios are ratios of wall-time medians relative to native Python,
  not claims about general application performance or statistical significance.
* Normal garbage collection remains enabled. No best-of cherry-picking, automatic
  threshold, CPU affinity change or process priority modification occurs.
* JSON records Python/platform/Decimal context, clock resolution, exact source,
  source hashes, repository head/dirty status and a digest of Python runtime
  sources plus this harness. Very short cases are timer-sensitive: increase
  iterations instead of interpreting noise as a speedup.

The unit suite checks all three BSL routes, independent expected answers, repeated-run
state reset, type-sensitive mismatch rejection, report structure and experimental
opt-in. Unit runs are correctness checks, **not** published performance evidence.

## GitHub Actions timing reference

`Performance reference` is an independent job in the `Test and build` workflow,
next to the JavaScript job, with no `needs` dependency in either direction. It
does not gate the build verdict, packaging, release, heavy tests or native-1C,
and it does not wait for PR-base admission. It runs for draft/stacked PRs, main
pushes, tag pushes and manual dispatch, using the main workflow triggers. The
standalone `performance.yml` is removed so events do not launch duplicate timing
runs. Cancellation follows the main workflow concurrency policy. The checkout is
the exact PR head (or dispatch SHA), not a synthetic merge commit. It uses read-only permissions and no secrets.

Open its **Summary** for the native Python / Python classes / BSL direct median
milliseconds and time ratios (native = 1×). The raw artifact retains every sample,
source hashes, environment and setup/first-call timings. Nine rounds at 100000
iterations are references, not a performance SLA; noisy runners affect numbers.
There are **no speed thresholds**. A wrong result, setup failure or invalid report
still fails the job rather than displaying an apparently successful timing. Such
a failure can make the overall workflow conclusion red, but no other job depends
on this result. Repository branch-protection settings are not changed here.

The third column uses the public default API. On a backend that recompiles inside
`execute_program`, that cost belongs to its measured call; it is not represented
as prepared-code execution. The exact API appears below the table.

### Prepared execution is a separate reference

`--bsl-route prepared` calls `Interpreter().prepare_program(parsed_ast)` once in
setup, then measures public `execute_prepared(plan)` against the same live VM.
Parsing, lowering and source-map construction are outside its timed execution.
The first invocation and the complete preparation cost remain explicit fields.
No hidden cache is introduced; the benchmark owns and reuses its prepared plan.

CI now appends a **second table** for prepared execution, retaining the original
public-default table and separate JSON/Markdown artifacts. Both compare native
Python / Python with yadinassi classes / BSL, and both validate every result.
They must not be conflated: the default `execute_program` table includes internal
preparation; the prepared table does not. First-call and preparation milliseconds
are also visible below each timing table.

### Ratio color indicators

Both timing tables decorate only the three ratio columns: 🟩 for 0 ≤ ratio < 2,
🟨 for 2 ≤ ratio ≤ 3 (including both endpoints), and 🟧 for ratio > 3. The category
uses the unrounded ratio; the printed number still has two decimal places.
Timing, preparation and first-call cells remain unchanged. These are visual
references only, not pass/fail gates.

GitHub's [markup sanitization](https://github.com/github/markup#github-markup)
removes inline styles, so custom cell backgrounds and a precise dark-yellow shade
are not dependable in Actions Summary. Colored square indicators preserve the
meaning in supported Markdown without CSS; the yellow shade depends on the
viewer's emoji font. Numeric values and the explicit legend remain readable
without relying on color. Summary Markdown and its artifact use the same renderer.

## Extended reference workloads

The same independent performance job appends extended default/prepared tables
and saves `extended-default.json/.md` and `extended-prepared.json/.md` inside the
existing artifact. Core reference tables and job dependencies are unchanged.
Run the reviewed, repository-owned runner (not an attachment script):

```sh
python -m unittest tests.test_benchmark_extended_layers
python scripts/benchmark_extended_layers.py --iterations 64 --rounds 5 --bsl-route default --output /tmp/extended-default.json --summary /tmp/extended-default.md
python scripts/benchmark_extended_layers.py --iterations 64 --rounds 5 --bsl-route prepared --output /tmp/extended-prepared.json --summary /tmp/extended-prepared.md
```

The bounded reference uses 64 operations and five rounds, not the core table's
100000 iterations. Select workloads with repeated `--case`; accepted sizes are
1..1000, rounds 3..20. Tiny unit runs establish correctness, not useful timings.

| Case | Work and honest comparison boundary |
|---|---|
| `structure.fields` | Mutable field write/read with Decimal checksum; Python dict vs BSL Structure. |
| `valuetable.build_scan` | Build one column, populate and read numeric rows; Python list of dicts is a bounded reference, not a full ValueTable implementation. |
| `valuelist.build_scan` | Construct and traverse indexed value items; complete resulting sequence checked outside timing. |
| `types.adjust_value` | Bounded two-decimal half-up rounding vs NumberQualifiers/TypeDescription; no claim of general type adjustment equivalence. |
| `json.roundtrip` | Writer/reader construction and string-array roundtrip, Unicode/escaping and actual decoded contents checked. |
| `xml.scalar_codec` | Supported numeric XMLString/XMLValue roundtrip. |
| `file.stat` | Open/fstat/close a regular 4096-byte temporary file; BSL additionally enforces its access envelope. |
| `file.binary_roundtrip` | Read and overwrite identical bytes to a different temporary output per layer; remove output before each sample, verify all bytes afterwards. |
| `xml.roundtrip` | XML numeric-attribute serialization/parsing; verify complete output structure and checksum. The known missing direct XMLWriter constructor is explicit unsupported/N/A, without legacy fallback; other errors fail. |
| `db.count` | Same fresh SQLite file, 32 canonically seeded warehouses. Raw SQLite COUNT omits BSL catalog/query admission, so ratios include that envelope and algorithm differences. |
| `db.update` | Canonical read/modify/write existing catalog item; reset before each sample and canonical persisted-value readback after it. No native Python ratio: raw UPDATE omits writer semantics. Not a crash-durability test. |
| `form.event` | Real FormSession command dispatch and snapshot; open/setup outside timer, counter reset inside handler. BSL-only, no invented Python/classes equivalent. |
| `form.open` | Actual FormSession construction, direct open, managed close dispatch and interpreter teardown. BSL-only lifecycle, not a prepared-module measurement. |

Forms appear only in the default extended table. An explicitly requested prepared
form case is rejected: FormSession is not `execute_prepared`. For other cases,
BSL default uses `execute_program(preparsed_ast)` including internal preparation;
prepared creates one explicit plan in setup and measures `execute_prepared(plan)`.
No hidden legacy fallback is used. Missing comparisons display `—` and an explicit
`unsupported` or `not_comparable` reason; they are never zero or ratios.

Shared fixture/BSL preparation, first invocation and per-sample reset time are
recorded separately. One untimed warmup follows the checked first invocation.
Execution order rotates through available layers; every timed result is validated
outside its timer. JSON retains wall/CPU samples, median/min/max/MAD, source/runner
hashes, exact commit and environment. Colored indicators remain only in ratio
cells, with the same <2 / 2..3 / >3 legend; setup and all timings stay uncolored.

Each filesystem/database case owns a fresh temporary directory and uses no user
files or existing database. ExitStack closes VMs/connections and removes fixtures
on success and failure. File measurements use warm OS/page cache, without fsync,
cold-storage or power-loss guarantees. Normal GC stays enabled. No performance
threshold is added: incorrect results, unexpected unsupported operations or
malformed reports fail, while the one declared unavailable XML capability is N/A.

## Separate untimed call diagnostics

After **all** core/extended timing commands, a separate Python process runs
`benchmark_diagnostics.py`. The timing runners never import or enable this
profiler. Diagnostic overhead therefore cannot enter their measured samples.
It is a current-thread `sys.setprofile` observer, not production instrumentation,
a runtime cache or a changed validation policy. Existing profiler state is not
overwritten; exceptions always remove this runner's observer.

```sh
python -m unittest tests.test_benchmark_diagnostics
python scripts/benchmark_diagnostics.py --iterations 8 --output /tmp/diagnostics.json --summary /tmp/diagnostics.md
```

CI adds `diagnostics.json/.md` to the same artifact and an explicitly **untimed**
Summary table. Counts have no speed thresholds, timing ratios or color categories.
A checked initial call and warmup precede one instrumented call per layer; fixture
setup, prepared-module construction, resets and post-call correctness checks are
excluded. Default still counts internal compilation performed by execute_program.
Form opening still includes its actual compilation/lifecycle; forms are not
relabeled as prepared-module execution. JSON retains absent-baseline reasons.

Named counters cover Python entries, built-in compile, SourceMap.compile,
recursive prepared-AST snapshots, catalog transaction begin, read_source, DDL and
canonical checks, recursive configuration equality, direct/base boundary checks,
catalog ownership/member dispatch and live source-reference construction.
Targets are matched by exact repository source filename and function name and
validated to exist before the run; recursive calls count separately. These are
non-additive observations of related paths, not disjoint cost percentages.
Builtin compile includes parsing-to-AST uses, so it is not synonymous with a
completed executable module. Python-call counts exclude profiler callback work.

SQLite execute/executemany/executescript count **Python SQLite API invocations**,
including Connection and Cursor methods. They do not count executed SQL
statements, rows, triggers, SQLite VM instructions or time. One executescript or
executemany API call may issue many statements. Only the current Python thread
is observed. No SQL trace hook is installed on application connections.

COUNT diagnostics hold query count fixed at eight and seed 32, 128 and 512 rows
in separate fresh databases (custom `--count-rows`, bounded 1..1024). Canonical
seeding is outside instrumentation. Increasing Python calls at stable execute
counts can identify row materialization; constant counts alone do not prove
constant work or latency. Raw SQLite still omits the catalog/query protocol.
`--iterations` is bounded 1..64, independently of timing workload sizes.

The audit's profiles were on an older commit and must not be attributed to a
new head. These counters make repeatable source-bound comparisons possible;
they do not yet implement any proposed cache, SQL aggregate pushdown, weaker
schema validation, local promotion or Map/byref specialization. Such changes
need separate current-state/transaction/ownership and semantic tests. In
particular, schema_version alone cannot validate current configuration data.
