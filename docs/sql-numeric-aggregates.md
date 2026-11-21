# SQL numeric aggregate candidate

This extends the existing closed catalog COUNT physical plan with one global
aggregate row containing SUM/AVG over direct Number fields and optional COUNT(*).
Several projections share one SQL aggregate statement. No Python row scan is
performed after the existing complete-source validation/identity proof.

## Deliberate numerical contract

SQLite evaluates `SUM(CAST(column AS REAL))` and `AVG(CAST(column AS REAL))`.
Computation therefore uses binary floating point and may lose precision or differ
from the Decimal residual executor, including cancellation/accumulation effects.
This is the requested SQL-computation tradeoff, **not** exact Decimal/native 1C
parity. Outputs are converted to Decimal and rounded half-even to the existing
result descriptor's scale (SUM: source scale; AVG: 10). Nonfinite and out-of-range
results fail explicitly. Empty inputs produce the existing NULL for SUM/AVG and
zero for COUNT. No schema, persisted value, write codec or storage precision is
changed; numeric storage remains the original validated Decimal text.

## Authority and resource boundary

The physical request contains only a bounded tuple of closed operation names and
logical UUID field identifiers. The backend resolves and quotes physical names
from its admitted layout; the caller cannot provide SQL or physical identifiers.
The same readonly snapshot first proves all persisted scalar values, including
unprojected fields, and normalized UUID uniqueness using the COUNT proof. Cached
proofs remain handle/epoch-local with existing external-write, own-writer and
failed-close invalidation. Enum-bound paths retain the existing before/after live
owner check and lexical snapshot witness. The result counts input rows and charges
the same bound input column budget as residual loading. Projection count is capped
at 64 and result resource limits remain enforced.

## Explicit residual shapes and next steps

Grouping, WHERE/HAVING, DISTINCT aggregate values, joins, arithmetic arguments,
sections/documents/registers, external/temporary sources and active transactions
are not selected by this candidate; they keep the existing relational executor.
There is no exception-based fallback: corruption/authority/errors are not hidden.
A missing provider capability or a documented unsupported physical shape declines.
MainDemo's current catalog metadata has reference fields but no Number catalog
fields; this slice does **not** claim to accelerate its document/section sums.

GROUP BY requires a separate contract for first-occurrence output ordering,
collation, NULL and typed key equivalence. Raw SQLite grouping cannot silently
replace the existing normalized key semantics. A future slice should begin with
proved typed key domains and explicit ordering rather than relax those guards.

Evidence consists of repository runtime differential cases (exact small values),
SQL no-materialization assertions, mixed aggregate metadata/budgets, readonly
storage-byte preservation and integrity/epoch invalidation tests. No new native
1C capture is claimed.

The enum-bound numeric regression creates a fresh supported inventory-enum-v1
configuration with a Number catalog attribute before normal preparation/import.
It does not mutate an admitted MainDemo schema or claim new native evidence.
