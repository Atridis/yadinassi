# Direct literal output to a list collector

A closed standalone BSL unit can emit a literal string to a Python
`list.append` output collector without publishing and reloading every module
slot for every message. The compiler admits only calls in statement position
with exactly one string literal, and only when the rest of the unit has no
opaque operations. At invocation it checks the live service and its
presentation implementation, the interpreter and the exact output sink. The
canonical string is appended unchanged. Counter and arithmetic lowering
remain the ordinary Decimal-compatible form.

A replaced service, state outside the scalar proof, or a different sink
selects the ordinary prepared plan. This includes Python callbacks that read
or mutate the module namespace, a list subclass, `print` (which may use a
custom stream), and configured/verified execution. Such callbacks still see
all module variables at each output call. No attempt is made to classify
arbitrary Python callbacks as pure.
