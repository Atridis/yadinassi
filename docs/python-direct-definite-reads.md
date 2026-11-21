# Definite scalar module reads

The direct compiler now proves exact-scalar islands at preparation time. A
module name written by a pure scalar expression can be read with `state[key]`
instead of `state.get(key, UNSET)` plus a missing-name branch. Proven pure For
loops also use direct reads for their counter condition and increment. Stores
remain immediate dictionary writes: no private cache, flush, VM dispatcher,
lease or delayed error-state publication is introduced.

Unknown operations, source/host calls, references, collection operations and
unknown operand types terminate the proof. Both If paths are intersected; loop
bodies are first checked without recording optimizations before entry facts may
cross the backedge. Zero iterations never prove body-created names. Routine
locals and globals are unchanged. Explicit authority checkpoints disable this
optimization. This is the existing trusted standalone execution contract, not
support for arbitrary concurrent mutation of the dictionary or host tracing
that changes storage between Python instructions.

Focused tests compare enabled and disabled compilation for host deletion,
clear/update, counter mutation, byref writes, unknown host operators, branches,
zero iterations and exception partial state. All 10 pass; default API/CLI smoke
suite also passes. No parity claim for other default-route limitations.

A nine-pair alternating measurement (20,000 iterations, same process, preparation
excluded, equal result controls) measured module arithmetic median 7.522 ms
before and 5.974 ms after. Private routine arithmetic measured 4.296 / 4.253 ms;
source-call loop 8.561 / 8.073 ms. The latter two are unchanged generated paths:
these small differences are noise, not attributed improvements. No thresholds
are imposed. Preparation cost and raw rows are retained in the measurement
artifact. This slice improves dictionary reads, not Python local-slot storage.
