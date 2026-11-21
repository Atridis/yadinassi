# Bounded direct Structure equality and collection presentation

Two independent representation leaks became reachable after the shallow
`FillPropertyValues` adapter was enabled:

* `test_cycles_remain_references`: the copied field correctly retained its
  original reference, but Python dict equality recursively compared two distinct
  direct Structures as equal. Exact direct Structures now use identity for `=`
  and `<>`, independently of the existing exact Array repair.
* The unchanged eight-record native owner checkpoint in
  `test_bounded_compact_command_matches_fresh_owner_output` exposed Python list
  repr through canonical `String`. Exact direct Array, Structure and Map values
  now present as `Массив`, `Структура` and `Соответствие` without traversing payloads.

## Evidence and scope

The frozen `tests/fixtures/native_windows/collections.out` records distinct
restored mutable Structures comparing false for both `independent-equal` and
`repeated-reference`, and records the three presentation labels above. Self,
alias, equal-copy and cyclic Structure cases are separately checked against the
canonical compiled-strict backend; this is not a new native capture or a claim
that every collection kind has the same equality semantics. Map equality,
fixed collections and raw host dictionaries are not changed.

The Structure repair is an explicit experimental opt-in and part of the direct
backend repair set. Operand order and exact Date boundary rejection remain
intact. Non-collection comparisons retain separate Python `==` and `!=`
behavior, not negation of one custom operator. Payloads and mixed foreign
operands are not asked to compare themselves by the identity shortcut.

Presentation intercepts only the definition-time canonical `to_string`
HostFunction, for both named service resolution and an explicitly captured host
callable. User overrides keep their existing behavior. Exact class identity,
not mutable public class aliases or isinstance, selects the native containers.
All other values keep the existing canonical service behavior. Boundary
validation, pre-call guards, implementation-identity checks after argument
effects and final lifetime checks remain in place. No new host receiver or
transport authority, recursive traversal, legacy dispatch or VM fallback is
introduced.

Focused regressions cover source, AST, prepared, Execute and Eval routes,
hostile comparison/repr/string hooks, cyclic payloads, class rebinding, custom
service overrides, captured functions, implementation mutation and revocation.
The two previously failing tests pass unchanged. Other failures in the broader
property/value-table modules remain outside this slice. No full native parity
or performance improvement is claimed.
