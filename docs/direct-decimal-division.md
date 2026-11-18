# Direct Decimal division and signs

The direct translator formerly emitted Python `/`, which uses Decimal context
precision rather than the existing measured BSL division model. It now lowers
`/` to a pure exact-Decimal adapter calling `values.divide`: the bounded
nine-digit-block model with measured away-from-zero half ties (PR83). This is
shared scalar code, not an interpreter or legacy backend fallback. Existing
4096-digit work limits and finite-number checks remain in force.

Unary `+` preserves the Decimal, and unary `-` uses `copy_negate`; neither operation
rounds a long operand to the process Decimal context. This is necessary for
signed division to preserve the native-observed operands. Unknown host objects,
Decimal subclasses, and Boolean operands are rejected without arithmetic hooks.
Both operands are evaluated once, left to right, before admission. Ordinary
source-aware errors, catchability, and assignment atomicity remain unchanged.

The isolated experiment keeps its raw policy unless `decimal_division` repair
is selected. Public direct entries select it. Addition, multiplication, remainder,
string collation and unrelated scalar comparisons are not changed.

Validation distinguishes measured native observations from model extrapolation:
all 71 saved native division suffix records pass, plus saved quotient values,
exact rational model probes and context/resource tests. The entire numbers output
still differs in pre-existing string comparison records; this slice does not
claim full numbers parity or universal 1C numeric precision.

Compatibility/performance tradeoff: direct division now incurs the bounded integer
coefficient/rounding algorithm cost instead of a raw C Decimal division; no speedup
is claimed. The existing helper's resource ceiling now also applies to direct
execution (it is a Yadinassi work limit, not a measured 1C numeric maximum).
Python3.10 retains its existing diagnostic column limitation (statement column1
rather than expression column12 in the zero-division test); line and message are
preserved. The independent Python3.12 review reran35 tests:34 pass, one known
string-collation failure in full native numbers prefix.
