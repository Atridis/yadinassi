# Compile-local structural identities for source mapping

Baseline: `0074b66524ea14920793164858cf6f95415761fe`.

`SourceMap.compile` previously serialized matching expression subtrees repeatedly
with `ast.dump`. It now interns structural identities once per AST node during a
single compilation. Parent keys contain child identities rather than recursively
serialized strings. Scalar fields use `repr`, preserving the old distinctions
between bool/int, bytes/text and signed zero. Location attributes are excluded.
No runtime lookup, owner/grant cache, compiler policy relaxation or AST execution
change is introduced.

The index owns its AST keys only during compilation. The recursive visitor's
closure cycle is explicitly broken in `finally`, so those ASTs are released
without waiting for cyclic GC. A GC-disabled regression verifies this lifetime.

## Measurements and limits

After coordinating a CPU window, seven alternating fresh-process pairs compare
three new Interpreter/prepare/execute_prepared/close operations per process, with
unchanged regex source. Startup/import/source read is outside timing; lazy backend
imports are included. This is a **cold prepared-module workflow**, not a hot
execution benchmark or a direct CLI startup measurement.

- Median total: **539.99 → 481.12 ms**, approximately 10.9% lower.
- Median prepare component: **476.04 → 419.70 ms**, approximately 11.8% lower.
- Six of seven pairs improved. The first pair worsened about 6%; one baseline
  sample is unusually slow. All samples are retained, none filtered out.
- All 42 output records match by hash across every baseline/candidate operation.
- The earlier unsynchronized noisy run is retained as `preliminary-noisy.json`;
  it did not establish a stable gain and is not the reported final comparison.

Reproduce on the same Python with before/after worktrees:

```sh
python experiments/source_map_structures/measure.py BEFORE AFTER
```

`test_source_map_structure_index.py` independently uses the old dump matcher and
compares bytecode, nested constants, line/position and exception tables for regex,
numbers, dates, nested routines and a server routine. It also tests structural
identity distinctions and prompt index release.

The pre-existing array error-text mismatch in
`NakedErrorIntegrationTests.test_exact_source_errors_and_partial_effects` remains:
`list index out of range` versus `Индекс массива вне границ: 2` at the same source
position. Independent review reproduced it using the old matcher too. Its
assertion is unchanged. No full CI or native parity claim is made.
