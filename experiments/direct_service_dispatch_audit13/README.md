# Audit13 service-dispatch measurement

Base a1fc1d6d. This differs from the unaccepted audit12 variant: three repeated
imports (TypeOf, internal serialization, Eval marker) now affect the common path.
The candidate hoists canonical ABI bindings and retains regex implementations
with an identity set. Live registry, argument, implementation-mutation and owner
checks remain in place. Internal module-constant reassignment is not a public
registration API; canonical identities are intentionally pinned.

Both other correctness workers explicitly held tests. Seven alternating fresh
process pairs, 100000 calls per case, three measured repetitions after warmup:

| Case | Baseline median ms | Candidate median ms | Improved pairs |
|---|---:|---:|---:|
| StrLen | 1067.38 | 693.43 | 7/7 |
| Same-module control | 44.02 | 44.91 | 4/7 |

All output hashes agree. Target-path reduction is about 35%; the control is
roughly unchanged with substantial scheduling outliers (not a claimed speedup).
This is not an application-wide or native-platform speed claim. The candidate
was an uncommitted diff during measurement, so both recorded Git HEADs identify
the baseline; the implementation diff in this commit defines the candidate.

Tests retain registered overrides, argument-time implementation mutation,
omissions, Eval scopes and serialization behavior. Added unhashable callable
coverage rejects equality/hash-based specialization. Static review found no
blockers; strong references to canonical regex functions prevent id reuse.
