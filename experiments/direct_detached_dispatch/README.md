# Exact detached-receiver dispatch

Base e43ff4e8. Seven isolated alternating fresh-process pairs, 50000 canonical
BSLArray.Get calls, three timed repetitions after warmup. All output hashes agree.

| Case | Before median ms | After median ms | Improved pairs |
|---|---:|---:|---:|
| BSLArray.Get | 486.81 | 325.42 | 7/7 |
| Same-module control | 29.00 | 29.58 | 5/7 |

Only the formerly unconditional detached-type return groups move before the long
owner chain. Current boundary checks and root access precede the fast path.
Exact retained type identities exclude subclasses and avoid custom metaclass
comparison/hash dispatch. Table rows/columns/indexes, list items, Query, metadata
and all database-owned receivers retain their previous ownership validation.
Detached public protocols retain their external-access and resource guards.

The marker-import experiment is separate and was not accepted: its control
improved almost proportionally, so its apparent gain was not distinguishable
from noise. No marker hoisting is included here.

An earlier interrupted mixed-load attempt produced no retained samples. These
complete results were recorded after all correctness processes ended and both
workers explicitly released CPU. Candidate was an uncommitted diff while timing;
the implementation in this commit defines it. This is a local microbenchmark,
not application-wide or native 1C performance evidence.
