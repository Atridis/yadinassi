# Dynamic complex-index actuals

A dynamic host call may request either a value or a reference for the same
indexed actual. For a complex index expression the compiler now selects the
reader/reference constructor first and emits the index subtree once. It does
not retain an index temporary, insert a Python wrapper frame, replay effects,
or duplicate a recursively nested expression.

Diagnostic migration: a failure of the selected complex indexing operation is
located at the Index expression's token in both modes. The previous text
compiler used the outer callee token for reference mode and the Index token for
value mode. Child failures (for example division by zero inside the index)
retain their own source positions. Existing simple Name/Literal index cases
retain their previous two distinct call-site positions. Exception types,
catchability, argument order, authority checks, partial effects and object
lifetimes are unchanged by this position-only normalization.

This avoids introducing runtime-frame inspection or a mutable diagnostic
side-table solely to preserve an incidental distinction in columns.
