# Pure module specialization with database capabilities

Previously, merely providing database external names or a Query constructor
turned off both definite-read and native-array analysis for the entire module.
Now the existing compile-time analyses accept explicit opaque external names.
External reads, writes and loop counters terminate the relevant facts. Query
construction and ordinary host calls remain effect boundaries; independent
pure computations before or after them can regain facts through assignments.
A custom Array constructor still disables array inference. Explicit authority
checkpoints still disable both analyses. No runtime guard or dispatcher is added.

This applies only to module-level numeric/array islands. Routine bodies remain
excluded. There is no general alias graph, deferred publication, cached value,
SQL specialization or claim that Query/SQLite becomes faster. Callback writes
and deletions remain visible. The Get callback regression covers the existing early rejection of unknown
index values; no redundant extra inference condition was added.

Tests assert identical generated code for a pure module with and without DB
capabilities; no extra dict.get/type/index checks in the proven kernels. Negative
cases exercise opaque getter/setter/counter receiver replacement, scalar deletion,
Query-constructor callbacks, custom Array construction and authority profiles.
A real database scenario reads Catalogs, constructs/sums an array and executes a
Query, checking both computational and DB results. 33 focused tests pass.

## Final paired measurements

Baseline local `3c720015` is exact-tree equivalent to public `d6e6e6d0`.
Five alternating fresh-process pairs on shared Linux/CPython 3.12.14; 10,000-
iteration kernels, median of three repetitions per cell. Database setup is
excluded. Prepared timings include execute_prepared admission but not initial
compilation; execute(source) includes parse and compilation. Final changed-file
SHA256, raw pairs and reproducible commands are in [`experiments/db_independent_facts`](https://github.com/Atridis/yadinassi/tree/713fb157cac984d8918681524848efa5f64f6b70/experiments/db_independent_facts).

Median milliseconds, baseline → candidate:

| Kernel / VM | Prepared | execute(source) |
|---|---:|---:|
| Numeric / database | 2.818 → 2.137 | 4.409 → 3.038 |
| Array / database | 10.353 → 6.612 | 15.129 → 9.511 |
| Numeric / plain | 2.209 → 2.094 | 3.018 → 3.141 |
| Array / plain | 6.453 → 6.727 | 9.335 → 9.321 |

All result controls agree. Plain timings vary by roughly ±5%, including regressions in some cells;
no general improvement is claimed for those already-specialized kernels. This is
not a claim of universal speedup. The intended improvement is removing the
unnecessary whole-module penalty for having database capabilities available.
