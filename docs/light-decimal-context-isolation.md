# Extended benchmark Decimal context isolation

On exact head `3260511dfd4bc57532908945975c68c107383c40`, the complete light
partition ran 12,073 tests with 1,276 errors and 304 failures. Five newly failing
methods, compared with the earlier b97d5fce run, all asserted that Decimal's
ambient Inexact flag stayed clear. Each of those five passes independently on
both exact revisions.

A six-test sequence reproduced the cause: the extended reference workload test
passes but leaves ambient Inexact/Rounded flags set by intentional plain-Python
`Decimal.quantize` in `types.adjust_value`. The following five runtime tests then
inherit dirty flags in their local contexts and fail. The same sequence fails
on exact immediate parent `d16a63758e490d9b11ec0062f310ce3bdd91a694`.

The repair is test-only. Each extended benchmark test enters a local Decimal
context and restores the original context through unittest cleanup, including
on failure. Python 3.10 is supported. No runtime assertion, test selection,
benchmark workload, timed region, sample, profiler, or production code changes.
A regression executes the actual reference workload fixture and verifies caller
context identity, precision, rounding, traps and flags afterward.

This fixes test-order pollution, not five separate runtime semantics bugs. The
remaining light failures are not declared fixed by this slice, and this report
makes no benchmark performance claim.

Verification: all four benchmark test modules followed by those five original
runtime tests pass (45 tests) in normal and optimized runs on both Python 3.12
and 3.10. The exact-parent six-test sequence still reproduces all five failures.
A new complete light run after this isolated fix has not yet been performed.
