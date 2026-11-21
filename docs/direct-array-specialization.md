# Compile-time native Array operations

A small forward pass (`python_direct_arrays.array_facts`) records exact native
list receivers and, separately, scalar-content facts. It emits no runtime
registry, wrapper, guard or VM fallback. The existing generic direct route
remains for expressions without proof. Existing scalar definite-read analysis
is unchanged; routine bodies and complex branch/control flow are not analyzed
by this initial slice.

Fresh Array construction, simple aliases and callback-free list operations can
retain receiver facts. Unknown effects clear them. Argument lists and receiver/
index expressions are analyzed in evaluation order; facts cannot cross an
unknown callback. A known receiver is still evaluated/bound BEFORE argument
effects, so a callback rebinding its source variable cannot redirect the call.
Opaque array contents do not become scalar: reading them may end operator proof,
while already-proven receiver identity can still select native list operations.
No alias graph is built: adding unknown contents conservatively drops every
scalar-array-content fact.

For loops need an invariant callback-free body and no writes to their counter.
Checked-index conversion is omitted only for proven nonnegative integers within
`sys.maxsize`. Literal and len-derived facts are bounded; addition/multiplication
do not preserve the bound. Subtraction of two bounded nonnegative integers can
supply a bounded (possibly negative) upper limit such as Count()-1. The loop's
post-exit counter is NOT treated as bounded: its final increment can exceed the
upper bound. Huge Decimals retain comparison-before-int through the original
narrow checked operation. The resulting native list access still checks actual
bounds, including after alias Clear and on empty arrays. Out-of-range diagnostic
wording may be Python's list wording; exact native wording is not claimed.

The pass is active only with live module state and array_index_contract, without
authority_checkpoints or declared constructor overrides. It does not weaken
those modes. NoSourceMap changes; no production guard removal.

## Supported and excluded host effects

Ordinary explicit host callbacks, receiver/argument ordering, rebinding, aliases
and opaque operators remain covered. Arbitrary trusted Python finalizers that
mutate the module namespace during a dict store are outside the supported
embedding contract. This is an explicit limitation, NOT a claim of arbitrary
Python sandbox safety and not a reason to introduce per-operation world scans.

Diagnostic example (not a supported-behavior regression test):

```python
from types import SimpleNamespace
state = {}
class Old:
    def __del__(self):
        state['a'] = SimpleNamespace(append=lambda value: print('host', value))
state['a'] = Old()
# Running `a=New Array; a.Add(1);` over this exact state can trigger Old.__del__
# during the first store and invalidate the compiler's array fact. Do NOT use
# such self-mutating finalizers in the trusted embedding.
```

The relevant native Array/Map/Structure and direct storage class definitions
were inspected and do not define __del__. Native containers can still contain
custom host values whose finalizers run on overwrite/clear; that distinction is
not hidden. Signal/concurrent/private-runtime mutation is likewise not an
arbitrary-Python safety guarantee of this standalone direct backend.

## Tests and measurements

15 focused tests cover100-element triplet, negative/fractional/Boolean indexes,
empty loops, alias clear, receiver callback rebinding, constructor-argument and
receiver-argument sequencing, counter modification, opaque contents/operators,
constructor overrides, huge Decimal rejection before integer expansion, and
Count()-1.49 targeted tests pass normally;15 new tests pass under `-O`.

Seven alternating fresh-process pairs againstb39f3219.10,000 Add +10,000 Get
operations, result49,995,000, array length10,000 and first/last values checked on
every warm run. Seven timed warm executions per process after two warmups;
public Interpreter.execute measured separately for cold parse/prepare/execute.

| | Before | After |
|---|---:|---:|
| Cold median ms |32.302|25.455|
| Warm median ms |11.675|6.855|

Median paired warm ratio1.703, range1.333–2.090. This is a consistent improvement
for this synthetic triplet, not a whole-application or real1C claim. GC stays
enabled, samples are unpinned, and other native/unknown-receiver workloads may
receive no specialization. Raw results and source hashes are retained in local
research artifacts. No full compatibility-suite claim.

Raw diagnostic profiles without Decimal-returning scalar repairs retain checked
index conversion, including rejection of Python-int Count results.
