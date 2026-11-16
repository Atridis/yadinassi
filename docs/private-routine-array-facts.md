# Native arrays in private routine scopes

The existing array analysis now also visits routine bodies, starting with no
caller facts. It receives the emitter's resolved opaque-name set: by-reference
parameters, module globals and external names. Val parameters and explicit local
Var declarations shadow globals/external names as before. A local assignment
can establish an exact fresh array; host/source calls invalidate facts.

Generated code uses the already-existing direct array paths. There are no new
runtime guards, VM dispatchers, deferred stores or interprocedural call graph.
Authority-checkpoint profiles and custom Array constructors retain their old
analysis restrictions. Ordinary opaque/byref/module accesses stay generic.

This deliberately does NOT infer that an unknown Val N is numeric or harmless.
`For i=0 To N-1` remains generic. Literal bounds and bounds derived from a proved
local array Count can specialize. Proving callback-free ownership of an array
under unknown comparisons would be a separate task, not an assumption here.

Tests cover literal and Count-derived loops, local/Val shadowing, byref aliasing,
module globals, host-held Reference replacement, unknown Val bounds, explicit
authority checkpoints, alias Clear and error effects. The compiler header now
accurately describes its production direct-default and diagnostic-profile roles;
module names and historical experiment documents are unchanged.

## Measurement

See experiments/routine_array_facts. Baseline b38dee3d is exact-tree equivalent
to public 3afcec50. CPython 3.12.14 on a shared Linux host, no CPU isolation.
Five alternating fresh-process pairs; each cell is median of three runs. All
three 10,000-element kernels check sum 49,995,000. Prepared and execute(source)
are reported separately, and unknown Val N remains a visible control.

Median milliseconds, baseline → candidate:

| Case | Prepared | execute(source) |
|---|---:|---:|
| Module control | 6.787 → 6.639 | 10.354 → 10.606 |
| Private routine, literal bound | 7.495 → 4.009 | 11.068 → 5.901 |
| Routine with unknown Val N | 7.223 → 7.442 | 11.168 → 11.461 |

The proven private routine is about 1.87× faster in this test. Unknown Val N is
not improved (roughly 3% slower here), and the module control is essentially
unchanged. This is not a claim that all functions or arbitrary array workloads
are specialized. Raw pairs and exact final runtime hashes are retained.
