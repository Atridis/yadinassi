# Scalar packet candidate

Base: e242b35c96af838fa9f1e9eb28571dd1fdbc617d. The candidate only adds an
exact-list immutable-scalar fast path in python_direct_server.transfer. A new
list is returned; None/NULL/exact str/bool/Decimal identities are preserved.
The root counts toward the unchanged 10,000-node budget. Nonflat packets and
subclasses retain the recursive path, including its depth/cycle/type checks.

`measure.py BASELINE CANDIDATE` runs seven alternating fresh-process pairs,
with three warm prepared executions per process, 10,000 real logical-server
calls per execution, and checked return values. Preparation is excluded.
Nested-packet and same-side calls are controls. All samples are retained.

`results.json` is the initial scalar-only run (before adding controls).
`controlled-results.json` is the second run using the checked-in script.
Both overlapped an independently running full-light test workload. They are
noisy diagnostic evidence, NOT accepted speedup measurements. First median:
317.50→248.06ms, 5/7 pairs faster. Second scalar median418.19→289.10ms,
but individual ratios range0.297–2.180; nested/control noise confirms contention.
The subsequent coordinated quiet run is recorded separately below.

Separately, current native run44098520311 CatalogQuery job134093310629 fails:
artifact14335746063 accepts native24 records but host output is empty.
On base e242b35c, unchanged `scripts/catalog_query_behavior/replay.py` reproduced the failure at
observe.bsl:33: R.Unload() returns BSLValueTable, whose Count receiver is rejected
by CatalogBoundary._catalog_owner as unregistered/foreign. This candidate does
not change ValueTable support or the native fixture. The later CatalogQuery fix
in55d210e2 is preserved by this integration.

## Coordinated quiet repeat

`quiet-results.json` uses the same checked-in script, baseline exact e242b35c and
candidate production from91237650; both trees were verified. Other workers paused
CPU jobs for this run. All seven scalar pairs improved: median302.83→206.69ms
for10,000 server calls (31.7% less elapsed time). Ratios0.519–0.730; no samples
were removed. Nested packets367.75→380.01ms (+3.3%, mixed pair directions);
same-side2.656→2.458ms is noisy and no speedup is claimed for that control.
This is a prepared scalar server-call scenario, not an overall application claim.

Correctness before integration:39 focused normal PASS,71 neighboring Python3.10
optimized PASS, independent39 optimized PASS and review without blockers,
including the original exact owned-SQLite full-client verifier. Integration over55d210e2 preserves the CatalogQuery fix.136 selected tests PASS
on Python3.12 normal and Python3.10 optimized, including original whole-client
and CatalogQuery exact replay plus server/byref/NoContext/dual/lifetime boundaries.
The benchmark remains measured on e242b35c/91237650, not on this later integration.
