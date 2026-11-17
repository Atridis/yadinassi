# Activation-local Eval preparation reuse

Baseline 58f67fa2. Seven alternating fresh-process pairs per case, 1000 identical
Eval("S+1") calls inside a function. Outer-module preparation is outside timing;
all fragment work and live binding construction remain inside. All 28 processes
returned 1000.

| Extra locals | Before median ms | After median ms | Improved pairs |
|---|---:|---:|---:|
| 0 | 1342.45 | 36.25 | 7/7 |
| 100 | 1554.70 | 173.95 | 7/7 |

This is a local repeated-expression improvement, not application-wide/native
speedup. Raw samples and driver are adjacent. Extra-local reference setup is
unchanged and remains measurable.

The private cache uses the existing Execute lifetime model: current activation
only, maximum 16 entries and 65536 retained source characters (not total code
memory), FIFO eviction. It stores facts/function/constants/source fields, never
AST, mutable Program, VM, caller bindings, scope or admission decisions. Keys
include current compilation contract, repairs, constructor/external names and
source/depth limits. Complete expression parsing remains mandatory before first
execution; failed preparation is not cached. Every hit rechecks live admission,
limits, current registration and ownership and creates/deactivates a fresh scope.

Tests cover current locals, constructor and persistent-routine readmission before
effects, limits, entry/text eviction, activation isolation and retained-unit
weakrefs. Existing nested Eval, byref, server/NoContext/dual and error tests remain.
