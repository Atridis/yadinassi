# Per-node local field and scalar facts

The direct compiler records facts for initialized scalar bindings and fresh local
Structures, including nested Structures and aliases. A proven field uses the
existing folded-key storage helper directly, without redispatching its receiver
or synchronizing module state for that field operation. Known numeric addition
is Python addition; known string concatenation still uses the existing BSL
conversion helper (including string plus number). For ordinary direct modules,
unresolved addition is Python addition too. A dynamic string-plus-number that
requires BSL coercion can therefore fail at the operator instead of retrying
with a BSL dispatcher. Owned/authority profiles retain their existing rules.

An opaque call/control operation invalidates the local environment. It does not
prevent later fresh assignments from establishing new facts. No receiver is
admitted at runtime and no caller-owned data graph is scanned. Module publication
and actual dynamic call boundaries remain unchanged.

For-loop analysis only retains facts when binding types, Structure field types
and the alias graph remain invariant across the body. A proven local integral
loop can emit `range` even outside a fully specialized module. A changing field
type or alias graph uses the existing dynamic
path. Unknown names, property failures, host operands, by-reference and source-
owned execution are not inferred safe. Current source/catalog/authority profiles
are excluded from this first per-node slice.

The existing whole-module table/item lowering is unchanged; this analysis does
not guess that arbitrary table cells contain numbers.

Simple local functions taking values and returning a pure expression over those
arguments are summarized at compile time. Such a call can participate in a
numeric expression without a per-iteration liveness check; functions that
access external state, take references, or call another routine are not
summarized by this rule.
