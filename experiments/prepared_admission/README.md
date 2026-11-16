# Prepared source admission without a repeated AST walk

Base: local `0f4d88eb`, tree equivalent to public `586dadfe`.

Prepared source is an owned snapshot, not a mutable-AST execution mode. Static
source checks run during preparation. Each handle retains immutable sets of
native collection constructor names, direct/grouped call names and declared
routines, plus the existing module declarations/layout and result-expression bit.
Execution checks the current constructor bindings and prior-routine registry
against those facts. This includes nested and unreachable source occurrences,
matching the previous conservative admission policy.

Every current VM class/ABI, namespace, host registry, restricted context,
active scheduler, family, target/backend/profile and DB-profile check remains.
Admission precedes contract-property access on rejected subclasses. Database
identity and permission checks at host boundaries are unchanged. Code handles
do not retain a VM or grant authority. No implicit fallback or identity cache.
The private snapshot/plan fields are not an API for hostile Python mutation.

Tests: 29 prepared/admission/database tests pass normally and under `-O`;
20 default-backend tests also pass normally. New tests prohibit source traversal,
parsing and compilation during prepared execution, and cover newly stale routine
names, grouped/dead calls, nested/dead constructors, unused overrides and invalid
live registries. Existing snapshot, source-coordinate, partial-state, declaration,
profile, DB-transfer/rebinding and callback tests are unchanged.

`benchmark.py BASE_REPO CANDIDATE_REPO --python PYTHON` runs seven alternating
pairs. Each worker prepares outside the timer, warms once, then measures 15
executions for 1 and 1000 increment statements. Every result is checked. This is
synthetic execution-only evidence, not cold preparation, business throughput or
native 1C parity. `results.json` contains all samples and exact source/runtime
hashes, without machine-specific paths. A preliminary run overlapped a default
smoke test and was discarded; saved results are a fresh isolated run.

Median execution times: 1 increment, 0.1028 → 0.0879 ms; 1000 increments,
5.2703 → 0.2071 ms (about 25.5× for this traversal-dominated synthetic case).
The small-module difference is much smaller and is not a general speed guarantee.
