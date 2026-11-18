# Direct Boolean equality domain

The direct backend previously let Python's `True == 1` apply not only to BSL
Number (exact Decimal), but also to host int/float and Decimal subclasses. The
existing numeric/Boolean contract only converts exact Number and Boolean; other
type pairs are unequal without host coercion. A new independent repair now wraps
the selected operator equality helpers: if either operand is exact bool, the
other must be exact bool or Decimal for equality to delegate. All other bool
pairs return False for `=` and True for `<>`, without calling host hooks.

Operand evaluation remains once, left to right. Exact out-of-range Date boundary
checks precede the Boolean mismatch, as in the canonical operator. Ordering
already had exact-type admission and is unchanged. Number/Boolean conversion is
not added to Map keys or Array.Find. Non-Boolean operators retain their previous
selected collection identity and host `__eq__`/`__ne__` paths independently.

Literal Boolean syntax must also use the guard; the previous primitive-literal
shortcut cannot prove that the other operand is a canonical scalar. Cached plans
use live operand types. Explicit experimental profiles without this repair keep
their old operators. No VM, legacy fallback, factory or host-member grant is added.

Evidence: `test_numeric_boolean_comparisons` documents Developer Guide 8.3.27
§4.5.3 and the existing canonical Number/Boolean operator contract. Python host
int/float/subclass rejection is an embedding-domain rule, not a newly measured
native 1C observation. No native expectations or stored captures are changed.
