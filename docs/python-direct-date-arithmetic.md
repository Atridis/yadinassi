# Direct Date arithmetic for inventory posting

The original Issue source queries stock at `Date + 1`. Previously the generated
Python operator raised TypeError; a test expecting posting refusal could pass
for that unrelated reason, and correcting the quantity still could not post.

BSLDate now implements Python `__add__` and `__sub__` through the existing pure
`shift_date` and `date_difference` algorithms. Ordinary numeric operations gain
no wrapper, dispatcher or extra emitter branch. Exact Decimal seconds are
required; Date subtraction returns the existing exact Decimal tick difference.
No reversed Number+Date operator or arbitrary host coercion is introduced.
Existing fractional rounding and uncertain-range markers remain unchanged.

The shortage test now checks the actual cancellation message, unchanged stored
movements, and successful posting after correcting quantity. Four new focused
tests compare direct/reference results, evaluation order, fractional ticks,
range behavior and rejection without reflected host callbacks. Together with
inventory scenarios and reports, 12 tests pass.

A separate existing range suite still exposes an unrelated direct Map gap:
lookup with an uncertain boundary Date does not raise. A baseline probe before
these changes also reports `caught=False`. This slice does not change Map keys.
