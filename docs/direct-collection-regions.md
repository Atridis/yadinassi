# Callback-free collection regions

The direct backend can specialize an initial straight-line sequence containing
fresh, untyped `ValueTable` and `ValueList` construction and numeric `For` loops.
This is not a second backend, a benchmark-name rewrite, or a legacy fallback.
Unsupported syntax terminates the proof and retains ordinary direct execution.
The tables, rows, columns, lists, and list items remain **eager canonical public
objects** throughout execution. There is no surrogate collection, delayed
publication, materialization step, or replay after an error.

## Bounded first stage

The compiler proves only exact numeric literals, numeric local assignments,
`+`, `-`, `*`, `%`, numeric `For`, table row `Add`/`Get` and field accesses, and
list `Add`/`Get` and `Value` reads. Names and iteration counts are not hard-coded.
Constructors and untyped column additions retain their existing public boundary.
No calls into source/host routines, callbacks, by-reference calls, handlers,
unknown operators, column changes inside loops, or collection replacement inside
loops are admitted. Routine bodies and configuration compilation are not enabled
by this first stage. Division and unary numeric helpers are deliberately excluded.

Before each loop, a no-effect gate verifies the current public ABI and canonical
object graph: exact receiver classes and instance fields, untyped/unindexed
schema, primitive values, live row/item identity membership, and list IDs and
revisions. A failed proof or gate selects ordinary direct operations **before
those operations run**, without catching their errors or repeating effects.
Gate dictionary keys are type-checked before dictionary lookup/comparison, so
host keys cannot introduce equality callbacks during admission. Previous values of
all overwritten loop bindings are also checked: unknown host objects, orphan
items, external weakref callbacks, and unproved descriptor payloads decline
acceleration. The fast flag is cleared after every loop, so ordinary assignments
between loops cannot leave a stale proof behind.

Closed leaf helpers preserve per-item limits, exact Decimal values, default
cells, row ownership, list IDs/revisions/indexes, and public object identity.
Each collection operation retains an authority/liveness check on entry and in
`finally`; closing or revoking the interpreter cannot be postponed until the
end of a whole loop. This uses the existing documented stable embedding
policy/storage contract, not a new assumption that `Interpreter.close()` is
unsupported during execution. Arbitrary concurrent Python monkeypatching is not
made safe or supported by the optimization.

## Validation and measurement

`tests/test_python_direct_collection_regions.py` compares ordinary direct and
specialized execution, including complete output graphs, partial exceptions,
unknown syntax, nested/zero loops, aliases, constructor and ABI changes,
instance method shadows, hostile dictionary keys, resource limits, and liveness.

For an uninstrumented, alternating end-to-end A/B using the existing reference
workloads and their full collection validation:

```
python scripts/benchmark_collection_regions.py --iterations 512 --rounds 15 --output collection-regions.json
```

The control disables region selection only. It does not select the legacy VM or
change source/results. Prepared and ordinary API timings are reported separately;
no timing threshold decides test success. Do not compare absolute times across
machines or run this alongside other CPU-heavy work.
