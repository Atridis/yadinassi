# Bounded direct FixedArray / FixedStructure snapshots

Base: `edd5e5ee88786ac76129524f8c9aac45bac550e2`.

Original source-session tests `test_fixed_array_nested_values` and
`test_fixed_structure_nested_immutable`, and the standalone original fixed-string
constructor test, failed at compiler constructor admission. All three pass after
this slice, with unchanged tests and no VM fallback.

FixedArray accepts exact direct lists and canonical arrays. A single recursion
creates canonical fixed arrays for directly nested arrays, including mixed
canonical/direct roots. Repeated acyclic branches create independent snapshots;
cycles fail before assignment. Structure/map values and existing fixed arrays
retain their references. FixedStructure uses the canonical string constructor or
a temporary view of direct Structure storage; the canonical constructor creates
the shallow snapshot, retaining value aliases and original spelling.

The finite source boundary exposes these fixed values' existing public reads,
methods, indexing and iteration. Writes fail, private Python storage remains
inaccessible, and each boundary retains runtime checks. Constructor registration
is checked before arguments, after arguments and after the current policy check.
The existing `call_value` operation and captured factory name are preserved,
including PermissionError conversion. No binding, scope or authority cache added.

Independent review found and corrected two bugs in the prototype: a canonical
array root containing direct list children did not freeze those children; and a
custom wrapper initially used the wrong policy event. Both have regressions.

## Reproduce

From repository root with project dependencies:

```
python experiments/direct_fixed_snapshots/check.py
python -O experiments/direct_fixed_snapshots/check.py
python experiments/direct_strings_parity/replay.py /path/to/native-artifact.zip
```

139 selected tests pass under Python 3.12 normal and Python 3.10 optimized.
The runner explicitly selects eight original standalone fixed tests, eight
original source-session cases, eight new direct regressions, and neighboring
ValueList, service, source session, catalog and document boundaries. New source,
AST/prepared and real source-session cases prohibit VM block/call_routine entry.
Independent reviewer ran seven new optimized tests (excluding the source-session
fixture), all passed.

Unchanged native strings replay is byte-exact in both runtimes: 385 observations,
386 physical lines, 13,707 bytes; SHA-256
`309d8a1b6ffd21ca578da5e2c2c161a7b28ce8b0692860effb6e92c0ad03a763`.
The replay checks original source/provenance hashes from native run 44107865305.
No native fixtures or CI gates were changed; this is not full native parity.

## Deliberate remaining scope

FixedMap is not enabled: direct `_TypedMap` and canonical Map have differing key
semantics, so a generic dictionary conversion would not establish correctness.
DynamicNew, copy-back constructors into mutable direct collections, first-class
Find and unrelated equality/import behavior remain outside this slice. An
exploratory full original fixed/session suite (115 tests) remains red, largely
because shared setups require FixedMap, with additional existing copy-back/import
and equality gaps. The selected runner is not a claim that those suites or the
whole source-wide CI pass. Direct fixed snapshots retain shallow mutable aliases;
existing session storage validation still rejects forbidden retained graphs.
