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
