# Plain Table first actual wall result (negative target verdict)

Three alternating fresh-process pairs, fixed hash seed, three timed repeats per
case after warmup. Baseline 14406828141a1fbc7e5b5505a12fc0f6be0b0803;
candidate b1688c3fd521d643f4c65cc5466012151d4403e6. Working trees clean;
package path, SHA/tree, exact Decimal sums and complete row contents checked.

| rows × columns | class baseline→candidate ms | prepared AST baseline→candidate ms |
|---|---:|---:|
|512 × 1|4.287 → 2.225|84.543 → 73.189|
|128 × 16|3.644 → 0.966|24.490 → 16.632|
|32 × 256|18.104 → 28.594|51.227 → 59.448|

Candidate/raw paired median ratios: classes 12.16×, 10.45×, 140.41×;
prepared AST 482.84×, 195.22×, 246.76×. Controls were noisy; do not treat the
AST median difference as an established speedup. Wide-schema case lost all
three pairs in both class and AST layers. This is NOT the requested 2–3× base.

The actual constructor is integrated, not a benchmark-only alternate class.
However kernel AddColumn still validates the entire graph and republishes the
whole schema on each added column. This repeated work remains a real design
problem, not an unavoidable compatibility requirement. Unified module-sync
also remains expensive independently of this Table patch. No GC suppression
or context-check removal was used to manufacture the numbers.

Raw artifacts: plain-table-wall-20261118/results.json in the local evidence
workspace. Growth-limit ablation has not yet been measured; no claim is made
about its cost.
