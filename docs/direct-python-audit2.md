# Second direct-Python performance iteration

This iteration builds on the public default switch (`ae96c19f`) and public API
triplet harness (`28917dc2`). The supplied perf_audit2 report inspected the older
`2081d2ef`; its claim that ordinary Interpreter still uses compiled-strict no
longer applies. Its diagnostic specializations are proposals, not measurements
of this combined candidate.

Included changes:

- Literal Structure field schemas are prepared once, retaining evaluation order,
  duplicate normalized keys, aliases and dynamic/invalid-schema behavior. See
  [schema measurements](direct-structure-literal-schema.md).
- SourceMap compilation normalizes each repeated expression once per compile and
  skips AST root kinds that cannot match. No global cache or runtime wrapper.
  Separate source-map tests compared all recursive code positions and bytecode
  with the preceding algorithm; the generated source is unchanged.
- Compile-time definite scalar module reads use direct dictionary indexing where
  presence and callback-free scalar operations are proved. Values are never
  snapshotted: every store still updates the live module dictionary. Unknown
  operations invalidate the proof. No delayed flush or new per-loop guard.

Array receiver/range inference, cached byref references and stable prepared host
calls are not implemented by this iteration. No claim of globally minimal
runtime machinery, native 1C equivalence or universally improved throughput.
The separate slice measurements are not a measurement of the combined tree.

## Compatibility and test status

The breaking default and existing documented gaps remain. In particular the
current direct error/source mapping requires Python 3.11+ position metadata.
The Python 3.10 regex CI job was reported with nine errors after the default
switch. Python 3.10 default execution is not currently supported by this route;
explicit legacy remains available. This iteration does not undo the default
switch or silently fall back to the VM to conceal those failures.

Full compatibility and green aggregate CI are not publication prerequisites for
this Draft. Focused checks are reported separately; unexecuted tests are not
counted as passing. The stacked PR base also conflicts with the current CI gate's
`main`-only admission rule; that gate is not relaxed here.

Combined focused validation: 91 tests PASS. The first combined run had one old
source-shape assertion requiring `.get`; it was updated to expect the new direct
subscript and additionally verify dictionary identity and resulting values.
Runtime source inventory is 357 and the new analysis module is included in the
existing byte-drift probes. No full-suite result is claimed.

The exact clean combined source `cdbd2c01` was also run through the public default
triplet harness (10,000 iterations, three rounds): all 45 timed result controls
matched. Median milliseconds, native Python / Python classes / default BSL:
arithmetic 1.90 / 10.65 / 4.12; calls 1.90 / 8.60 / 6.27;
byref 1.09 / 6.23 / 8.42; array 1.82 / 10.75 / 16.67;
map 6.37 / 15.34 / 23.60. This short run is not a paired speedup claim.
Default execute_program still includes lowering/compile on each invocation;
that cost is not silently removed. Raw setup, first execution, samples and
source hashes are in `experiments/audit2/default-triplet.json`.
