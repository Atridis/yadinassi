# SQL numeric aggregate candidate

This extends the existing closed catalog COUNT physical plan with one global
aggregate row containing SUM/AVG over direct Number fields and optional COUNT(*).
Several projections share one SQLite aggregate statement after the existing
complete-source validation/identity proof; the relational row loader is not used.

## Exact numerical contract

Catalog Numbers use metadata-scaled integers: SQLite INTEGER for precision
through 18, and an ordered 16-byte BLOB for precision through 38. A registered
SQLite aggregate accumulates coefficients in a Python integer with no REAL
conversion or SQLite 64-bit sum overflow. SUM keeps the source scale; AVG
uses the exact sum and row count, rounded half-even to ten places as in the
relational executor. Empty inputs produce NULL for SUM/AVG and zero for COUNT.
Unsupported shapes stay on the same exact relational implementation.

## Authority and resource boundary

The physical request contains only a bounded tuple of closed operation names and
logical UUID field identifiers. The backend resolves and quotes physical names
from its admitted layout; the caller cannot provide SQL or physical identifiers.
The readonly provider first validates persisted scalar values, including
unprojected fields, and normalized UUID uniqueness using the COUNT proof.
The existing view/handle scope and proof invalidation are unchanged. Enum-bound paths retain the existing before/after live
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

Evidence consists of repository runtime differential cases (including 38-digit
cancellation, integer totals larger than 64 bits and AVG ties),
SQL no-materialization assertions, mixed aggregate metadata/budgets, readonly
storage-byte preservation and integrity/epoch invalidation tests. No new native
1C capture is claimed.

The enum-bound numeric regression creates a fresh supported inventory-enum-v1
configuration with a Number catalog attribute before normal preparation/import.
It does not mutate an admitted MainDemo schema or claim new native evidence.
