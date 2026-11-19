# Bounded native-integer lane

The direct compiler may keep numbers as Python `int` inside a **closed scalar
module with repeated arithmetic in a loop**. One-off scalar statements and
loops without arithmetic retain their original compilation, avoiding the extra
two-body preparation cost. This is an implementation representation, not a second public BSL
numeric type. Final expression results and published variables remain Decimal.
There is no runtime arithmetic dispatcher, admission pass or input-data walk.

The first slice accepts initialized numeric literals/names, unary signs,
addition/subtraction/multiplication, and ascending literal `For` loops. Every
intermediate is conservatively bounded to at most 38 decimal digits, including
loop counters after their final increment. Loop assignments must be independent;
a recurrent accumulator is limited to `S = S + expression` or subtraction with
an expression independent of all other loop-assigned names. Its bound covers
all iteration prefixes; analysis does not unroll the loop.

Anything unproven retains existing Decimal compilation for the entire module:
fractions, division, mixed arithmetic, external input, calls, by-reference,
collections, branches, nested loops and more general recurrences. In particular,
integer division never silently becomes Python floating-point division. Existing
authority checks/publication and source-owned execution paths are not changed.

This deliberately narrow lane proves a useful implementation direction, not a
claim that every integer BSL operation has already been optimized. A future mixed
lane can use Python's native int/Decimal operator promotion where semantics are
proved; it must not add a Python dispatcher on every arithmetic operation.

A prepared plan makes **one entry decision** from the current Decimal context.
The integer body requires precision 38, Emax at least 37, Emin at most zero and
clamp disabled. Other contexts execute the original direct Decimal body, preserving
its overflow/trap behavior even when the context changed after preparation.
This is not a legacy interpreter fallback and does not catch or retry failures.
Literal scale/scientific notation and signed zero are preserved by declining the
lane; possible negative-zero products, negation and additive cancellation are
also left to Decimal, including the ambient ROUND_FLOOR case.
