# Explicit product namespace seam

The internal direct compiler accepts `prepare(..., external_names=(...))` with
`live_module_state` and `service_boundaries`. This is a compile-time tuple/list
of names from the product's trusted schema, not a snapshot of current values.
It must be available even before initial form data is populated.

For those names the emitter generates `context.external_get(name)` and
`context.external_set(name, value)`. No VM `semantic_name`, `set_variable` or
visitor is called. Product values are not copied into the module dictionary.
Routine parameters and explicit local Var declarations shadow external names;
ordinary private locals remain native Python locals. Module declaration/name
collisions and conditional Var shadowing are explicitly rejected. External
counter assignments, For increments (including Continue), and ForEach targets
also use the product setter. RHS evaluation precedes setter errors, including
readonly reserved properties such as ThisObject.

`BoundaryContext` grants no external namespace by default. A product-specific
context must implement the getter/setter and preserve its authority/type rules.
A form adapter should delegate to the existing form getters/setters, not write
`form._data` directly. This patch does not add that integration or authorize
configuration interpreters. It does not expose arbitrary Python members.

Bare external-name byref arguments still fail through
`context.external_reference`, preserving the existing managed-form limitation.
Val arguments read the current value. Event byref slots and handler exports are
a separate integration. External names used as callable names are explicitly
unsupported in this first seam; registered ordinary service names are unaffected.

Compile-time definite-read/array-flow optimizations are disabled for this
profile: product accessors can have effects. This changes no ordinary standalone
profile and adds no blanket runtime guard around its local operations.

Twelve focused tests cover initial schema without values, live callback updates,
parameter/local shadowing, implicit external assignment, readonly evaluation
order, byref refusal, Val reads, For/Continue/ForEach, default denial, and actual
form setter string adjustment plus host readonly protection. No form runtime
integration or full UI success is claimed by this commit.
