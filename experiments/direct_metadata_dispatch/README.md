# Exact detached-metadata receiver classification

Replace the generator in `_owns` with three direct exact-class identity checks.
This removes generator allocation from unrelated detached receiver dispatch without
changing metadata admission, graph validation, ownership, revocation or quotas.
Subclasses remain excluded; no user equality or hash hooks are invoked.

Run `measure.py detached BEFORE AFTER` with the repository Python environment.
Seven alternating fresh-process pairs each execute three timed prepared runs of
50,000 BSLArray.Get calls and a same-module function control. All result hashes
must agree. Values are microbenchmarks, not application-wide or native 1C parity.

`results_pre_xdto.json` records the first isolated run on 4fd3f870. Its control
was variable, so publication requires a second run after XDTO integration.
`results.json` records that confirming run on b2570dca.

Regression coverage: exact classes, rejected subclasses and user hook avoidance,
plus detached metadata and detached dispatch suites. All metadata graph checks
remain in place; this is not a metadata fingerprint cache.

## Results

First run: host median 382.17 -> 283.89 ms (7/7 faster raw pairs);
control 24.47 -> 22.48 ms, so a confirming run was required.
After XDTO integration: host median 394.37 -> 319.36 ms (19.0% lower,
5/7 faster raw pairs); control 25.86 -> 26.50 ms (2.5% slower).
All seven confirming pairs improve the host/control ratio, including two
system-wide timing outliers. This remains a noisy shared-host microbenchmark,
not a universal 19% application speedup. The tiny allocation removal is supported
by both series; no metadata safety checks were removed.
