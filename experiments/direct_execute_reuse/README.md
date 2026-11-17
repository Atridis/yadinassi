# Activation-local Execute preparation reuse

Baseline e62bbacaa1930532e507a18abca22099e922c796. Seven alternating pairs of
fresh Python 3.12 processes per case, 1000 identical Execute statements inside a
function. Timing excludes preparation of the outer module, includes all fragment
executions. All 28 processes returned 1000.

| Extra locals | Baseline median ms | Reuse median ms | Improved pairs |
|---|---:|---:|---:|
| 0 | 1127.12 | 17.56 | 7/7 |
| 100 | 1218.23 | 65.68 | 7/7 |

Raw samples and runnable driver are adjacent. Absolute timings are local and not
a native 1C comparison. Extra-local binding work remains unchanged.

The private cache belongs to the current boundary activation, not the VM or a
global registry. It retains only immutable source facts, generated function,
constants and source coordinates. It never retains AST, mutable Program, caller
scope, values, references, errors or admission decisions. Every invocation checks
current bindings and limits and creates/deactivates its own FragmentScope.

Keys include exact source, VM compilation contract, repairs, admitted constructor
and external-name sets, and source/depth limits. FIFO eviction bounds entries to
16 and retained input text to 65536 characters (not total generated-code bytes).
New activations do not reuse previous units. Parsing/compilation failures are not
cached. No persistent cache, disk format or option is introduced.

Regression tests exercise cache hits, fresh locals, current constructor admission,
source/depth limits, entry/text eviction, activation isolation and weak-reference
release. Existing nested Execute, byref, server/NoContext/dual, error coordinates
and revocation coverage remains in force. SearchDirection changes are retained.
