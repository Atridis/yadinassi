# Direct FixedMap snapshots

Base: `5ece2a22d0554c629e331649c2684dd4fda0c6fd`.

Three original source-session cases failed at unsupported FixedMap constructor
admission: assignment/read, dot/index access and nested-mutable rejection. They
now pass unchanged. This slice admits the canonical bilingual constructor and
exact FixedMap receiver using the existing fixed snapshot boundary. It adds no VM
fallback, source/form dispatcher or cache.

Canonical BSLMap input uses its existing shallow snapshot. An exact direct
`_TypedMap` is converted into a temporary canonical-key view and snapshotted by
BSLFixedMap. Key and value objects retain their identity; Boolean and Decimal
remain separate. Arbitrary host object keys use identity without hash/equality
hooks. The input is never mutated. Only exact supported map roots are admitted.

Direct Map has fewer value-key rules than canonical Map. Conversion therefore
rejects two distinct direct entries whose canonical tokens coincide (for example,
two separately allocated equal UUIDs), instead of silently dropping an entry.
The refusal is catchable and occurs before assignment. A single UUID key adopts
the canonical FixedMap value lookup contract. This is an explicit bounded
compatibility limit, not a repair to mutable `_TypedMap` semantics.

FixedMap indexing still rejects an absent key while Get returns Undefined;
an existing Undefined entry remains readable. Mutators and assignments reject;
iteration yields readonly pairs. Nested values remain shallow aliases, not newly
frozen graphs. Existing session validation still rejects forbidden mutable state.
Current factory identity, policy and runtime checks are reused unchanged.

## Verification

From repository root with project dependencies:

```
python experiments/direct_fixed_map/check.py
python -O experiments/direct_fixed_map/check.py
python experiments/direct_strings_parity/replay.py /path/to/native-artifact.zip
```

192 selected tests passed on Python 3.12 normal and Python 3.10 optimized:
7 new regressions, 14 original fixed-collection cases, 54 original source-session
cases, and neighboring fixed/list/source lifecycle boundaries. The new tests
cover source, AST and prepared construction with VM entry points forbidden.
Independent review ran all seven new tests under -O and found no blockers.

The complete original source-session pair has 63 tests, with nine remaining
errors in reusable routines, ValueStorage, standalone read-name resolution and
expectations of catchable exceptions at fail-closed authority boundaries. The
runner explicitly lists those exclusions. The broader fixed suite remains red
for copy-back constructors, imports, equality and other existing direct gaps.
No original test or fixture is modified; selected tests are not a full-CI claim.

Strings replay remains byte-exact on both runtimes: 385 observations, 386 physical
lines, 13,707 bytes, SHA-256
`309d8a1b6ffd21ca578da5e2c2c161a7b28ce8b0692860effb6e92c0ad03a763`.
The replay verifies original source/provenance hashes from native run 44107865305.
This is strings evidence, not full native parity. No performance claim is made.
