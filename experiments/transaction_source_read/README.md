# One source read per format-16 transaction

Baseline: `8da658715130a90a6a95b79e838f22d71f01d7ec`.

`SQLiteCatalogBackend._begin` used to call `read_source`, then `admit` read the
same source again in the same SQLite transaction. It now passes the local tuple
to a private admission helper. The public `admit` still reads fresh source.
Nothing is retained on the backend/view; this is not an admission cache.
The existing prepared-import cache and its publication point are unchanged.

All first-read checks (bytes/hashes, marker/profile, database identity, canonical
configuration and DDL), current backend config/domain equality, layout/document/
sequence checks and remaining register admission stay in place and in order.
Between read and admission there are no SQL writes or user callbacks.
The supported rollback journal prevents another connection committing during the
read transaction. A later transaction always rehashes current source. WAL is not
supported by this backend; no WAL guarantee is claimed or newly enabled.

## Reproduce

```sh
PYTHONPATH=tests:scripts:. python -B experiments/transaction_source_read/measure.py
PYTHONPATH=tests:scripts:. python -B experiments/transaction_source_read/profile_next.py
PYTHONPATH=tests:scripts:. python -B -m unittest test_sqlite_transaction_source
```

The timing script reconstructs **both** original `_begin` and `admit` functions
from the baseline commit, then alternates old/new order over seven pairs. Each
sample uses a fresh real MainDemoHost/SQLite fixture and the existing scalar
editor worker. Timing excludes fixture setup, includes the real Description and
Save paths, and verifies saved trimmed text and product warehouse count.
Warm medians exclude each fixture's first iteration; all raw samples including
first iterations are retained. Tests were finished before the published timing
run; an earlier run overlapping tests was discarded. Python 3.12.14, Linux.

| Actual operation | Before ms | After ms |
|---|---:|---:|
| Kind Description | 11.006 | 11.861 |
| Kind Save | 41.220 | 39.299 |
| Product Description | 10.487 | 10.630 |
| Product Save | 55.643 | 43.161 |

Product Save improved in all seven pair medians (~22% aggregate reduction).
Kind Save is noisy (two pair regressions), and Description does **not** improve.
Do not extrapolate these figures to all operations or add them to earlier gains.
A separate SQLite statement trace for read/write/read observed the full source
SELECT **6 times before, 3 after**. No reads were removed across transactions.

85 targeted tests passed normal and `-O`: transaction source tests, main-demo
storage admission, prepared source admission, read-handle lifecycle, direct
database and direct posting. Independent review passed 47 tests under `-O` and
found no blockers. New cases cover independent public admission, one source read
per transaction, concurrent writer refusal, changed bytes on the next begin,
rehashed drift, DDL and register-schema corruption. No full CI/native parity claim.

## Next audit8 candidates

`profile_next.json` profiles only 24 actual Description/Save actions, excluding
setup; profiling overhead means these durations are **not** timing evidence.
Remaining `_catalog_shape` work: 102 calls, 0.2743s cumulative of 1.8427s total
(~14.9%). This is the strongest next candidate in this workload, but a pure
shape reuse proposal must still validate current SQLite DDL and domain/schema
identity. No shape cache is introduced here.

`definite_module_reads`: two calls, 0.000032s cumulative; `_TypedMap.token` was
not called. Neither justifies additional machinery for this workload. Array/Map
kernels would need their own reproducible measurements. Specialized `_TypedMap`
must remain distinct from canonical BSLMap reference-key semantics. No locals
flush/snapshot scheme or speculative Map optimization was added.
