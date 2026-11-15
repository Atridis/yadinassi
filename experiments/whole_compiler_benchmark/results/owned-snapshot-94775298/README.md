# Whole-program owned snapshot: controlled 10M experiment

Experimental runtime source: `94775298e594eb025a8fcc362635d87e1199d8d8`.
Untouched interpreter oracle: `66a7ea6bcdfb7802091d27c1d881d209a49bef7a`.
This is **not production/default enablement**, full-suite approval, or a Python sandbox.
Owned execution ran only in isolated processes with original-AST monitoring explicitly
OFF. Its active AST mutation behavior differs from the existing fail-closed contract.

## Method

CPython 3.12.14, Linux x86-64, AMD EPYC 9V74 (full environment record alongside).
Three alternating triples, each sample a fresh process on the same machine:

1. Untouched interpreter, current interpreter, owned OFF strict.
2. Owned OFF strict, current interpreter, untouched interpreter.
3. Current interpreter, untouched interpreter, owned OFF strict.

Other local engineering tests were paused. Raw before/after system load is recorded;
this cannot guarantee absence of unrelated host activity. PYTHONHASHSEED=0,
PYTHONDONTWRITEBYTECODE=1, no optimization environment flag. The two-loop user source
is unchanged apart from previously documented Markdown multiplication/NBSP normalization.
All nine samples used source SHA256
`8df3bc2633b2c1fda1c3dc7b406c39ee24372843b1e83c3b0571b73f3a3b379a`
and returned exactly `149999945000000` for 10,000,000 iterations.

Execution elapsed includes admission/compilation and both measured blocks, but excludes
process startup/imports, VM construction and parsing. Parse and preparation time are recorded separately;
the preparation timer includes admission, ownership construction, lowering and Python compilation, not Python compilation alone. Preparation is **not** subtracted from the total. The timed block values originate in
the supplied BSL source. Independent block medians need not sum to total median.

## Medians (seconds)

| Mode | Empty loop | Arithmetic loop | Total execution | Admission/compile |
|---|---:|---:|---:|---:|
| Untouched interpreter | 18.788 | 68.764 | 88.202 | n/a |
| Current interpreter | 20.439 | 76.327 | 96.786 | n/a |
| Experimental owned OFF strict | 2.030 | 23.338 | 25.487 | 0.0669 |

Against the **untouched**, faster oracle, the experimental snapshot is 9.26x faster
for the empty loop, 2.95x for arithmetic, and 3.46x in total. This is not the former
narrow-backend result and must not be presented as equivalent full-monitor performance.
It is not a speed comparison to native 1C on another computer.

The current interpreter is **9.73% slower in total** than the untouched oracle
(approximately 11.0% arithmetic regression). This is an unresolved production blocker,
not a baseline to select for a more flattering acceleration ratio.

## Qualification remains incomplete

The frozen older `60ce508a` raw global OFF suite reached its declared 3600-second bound:
6950 completed cases, 37 failures, 3201 with observed compiled execution. It is
INCOMPLETE/FAILED, not a full PASS. Source-specific fixes and targeted checks are
separate evidence. The new experimental source has not completed a full fresh suite.
Historical Fill matrix replay passed locally on `03e6b3a0`; this is not fresh native
1C parity. Mutation-contract tests and separately isolated old-backend oracle tests
remain explicitly distinguished from positive strict compiled coverage.
