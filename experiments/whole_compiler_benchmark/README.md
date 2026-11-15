# Whole-program compiler benchmark

The input preserves the user-supplied empty and arithmetic loops and result
149999945000000 for 10,000,000 iterations. Only Markdown-escaped multiplication
and non-breaking indentation were normalized. Neither loop is recognized as a
special source pattern by this compiler.

## Experimental checkpoint 3281771e

CPython 3.12.14, Linux x86-64, AMD EPYC 9V74. Three alternating fresh-process
pairs used the refactored interpreter and compiled-strict inline-fast mode.
Three subsequent unchanged-source interpreter controls ran on the same idle
machine. Those controls were sequential, not interleaved pairs.

Median seconds, all checksums equal:

| Backend | Empty | Arithmetic | Whole program |
|---|---:|---:|---:|
| Unchanged interpreter (66a7ea6b) | 18.997 | 67.663 | 86.579 |
| Refactored interpreter (3281771e) | 20.049 | 80.265 | 100.217 |
| Compiled strict (3281771e) | 25.872 | 52.811 | 79.201 |

Against the unchanged oracle this is approximately 1.28× arithmetic speed and
1.09× whole-program speed, **but the empty loop is approximately 36% slower**.
The refactored interpreter itself regressed, so its larger relative speedup is
not a valid headline. These are development results, not production readiness.
The working branch subsequently changes both hot paths; these measurements do
not establish performance of later commits. There is no speed comparison to
native 1C measured on another machine and no transfer of earlier narrow-PoC
speedups to the general compiler.

Raw results and input hashes are under `results/3281771e`. Detailed node counters
were disabled; real inline block/fragment counts prove execution, while
`node_coverage=unobserved` explicitly avoids inventing per-node coverage. No
rejections or interpreter fallback occurred in the measured compiled samples.

## Reproduce one sample

From a clean checkout, using the same Python executable for both backends:

```
PYTHONPATH=. python experiments/whole_compiler_benchmark/run_sample.py --backend interpreter
PYTHONPATH=. python experiments/whole_compiler_benchmark/run_sample.py --backend compiled-strict
```

For an unchanged interpreter checkout, invoke this runner by its absolute path
while setting `PYTHONPATH` and working directory to that checkout. The runner
imports the compiler only for compiled-strict mode. Coordinate other CPU-heavy
work, alternate fresh processes, retain individual samples, and verify both
input hash and numerical checksum before summarizing results.
