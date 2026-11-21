# Standalone direct Eval requires a value

`Eval` / `Вычислить` accepts a single expression, even when its result is
discarded by the outer statement. The standalone direct fragment compiler had
requested the last expression's return value without requiring that its callee
be a function. Source-module Eval already enabled that requirement.

The fix enables the existing required-value contract for every Eval profile.
It does not change parsing, procedure/function metadata, constructor admission,
expression execution, host capabilities or error conversion. Ordinary statement
calls and Execute still allow procedures. A function returning Undefined is
still a function; it is not rejected based on its result.

The regression first appeared in the remaining FillPropertyValues test:
assignment and nested-expression forms correctly rejected the procedure, but
`Eval("FillPropertyValues(...)")` ran it. Tests now cover registered and captured
host procedures, persistent BSL procedures, nested/grouped Eval, aliases and
source/AST/prepared/Execute outer routes. Rejection precedes argument effects;
cached evaluation rechecks live function metadata. Explicit user overrides of
Eval remain unchanged. Existing lifetime, depth and retained-reference tests
remain part of the focused cohort. No legacy execution or fallback is added.

The unchanged original Eval helper and checkpoint source from `functions.bsl`
is replayed against all 30 frozen `eval.*` records in native_windows/functions.out.
This verifies existing native expression/reference/error behavior. That native
checkpoint does not directly probe a procedure passed to Eval; the new rejection
is grounded in the canonical expression-value contract and separate regression
controls, not advertised as a newly acquired native observation. Array/method
procedure metadata gaps outside this contract are not repaired here.
