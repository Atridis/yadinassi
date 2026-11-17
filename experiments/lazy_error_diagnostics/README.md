# Lazy handled diagnostics

Baseline `e00be58fa8b455f0247f382a8b24fcba7ec82edb`, candidate
`8a2cc088` (see full identities in results.json). Seven alternating fresh-process
pairs on CPython 3.12, coordinated CPU window. Each process prepares each source
once and measures three execute_prepared calls, with a fresh activation per call.
Each source handles 1000 decimal divisions by zero. Large cases declare 100 extra
functions. Source preparation/import is not included in the timings.

| Case | Before median ms | After median ms |
| --- | ---: | ---: |
| Small, silent handler | 34.46 | 2.47 |
| Large, silent handler | 119.00 | 2.52 |
| Large, ErrorDescription in handler | 142.37 | 21.49 |

All seven pairs improved in each case. All 126 result fingerprints matched,
including the exact formatted description and handled count. Samples, ordering,
Python version, source commits, and all individual timings are in results.json.
This is an exception-heavy prepared-workflow improvement, not an overall
application speed claim. The measured code predates the later correctness merge;
re-run correctness checks after integration, do not relabel these timings.

The handler keeps a scoped lazy record. Conversion occurs once on description
access or bare rethrow. Unobserved caught errors do not construct positions or
source lines. Observed errors reuse at most one code-position table and one
source-line table on the current activation. There is no global cache, traceback
cache, registry cache, or authorization cache. Changed code/source replaces the
single entry; no unbounded per-Execute accumulation.

Tests check exact cached/uncached diagnostics, source positions on Python 3.10
and 3.12, nested handlers, invalidated outer rethrow, live owners, arithmetic
rethrow origin, and immediate release of completed handler tracebacks with
cyclic GC disabled. Existing index-error text incompatibility is not changed.

Reproduce with the project Python environment:

```
python experiments/lazy_error_diagnostics/measure.py BEFORE_WORKTREE AFTER_WORKTREE
```

## Integration verification

Rebased on correctness commit `ef50997fd3f0f8a5f19d5304466a191a33142420`.
165 selected tests passed on Python 3.12 normally and Python 3.10 with `-O`.
The unchanged whole-client owned-SQLite replay still matches all 138 observations
and exact bytes in both managed-thick-file and standalone modes, exit 0 and
empty stderr. See integrated-replay.json. This is local replay, not a new native
1C run or proof of full CI success. The timing samples above remain tied to their
original baseline/candidate; integration did not silently relabel them.
