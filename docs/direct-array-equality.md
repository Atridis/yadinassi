# Bounded direct Array operator equality

This repair only changes `=` and `<>` when at least one operand is an exact
native list (the direct Array representation). Such comparisons use identity,
not contents. Both operands are evaluated exactly once, left to right. Payloads
are not traversed, compared, hashed or converted. Other operand pairs keep the
previous direct Python `==`/`!=` operators, separately; arbitrary host `__ne__`
is not rewritten as the negation of `__eq__`.

Evidence and existing contract:

* The accepted native tree-copy measurement's `TCArray` creates separate equal
  nested arrays; `TCCalibrate` requires both levels to compare unequal before
  testing Copy (`integrational_tests/measurements/tree_copy.bsl:550–551,652–653`).
* Existing fixed-collection tests cover mixed fixed/mutable kinds in both
  directions and require inequality. The legacy `values.equal` rejects distinct
  runtime types before dispatching equality. The new mixed-kind matrix keeps
  that existing behavior; it is not a new native measurement.
* Copy preserves the original cell references. Its unchanged `cg.Payload<>ca`
  assertion exposes operator semantics, not an incorrect copied graph.

This does not repair Map/Structure equality, change typed Find, change scalar
semantics or introduce VM fallback. The repair is explicit in the compiler's
repair set and enabled for the direct backend. Existing experimental profiles
without that repair remain unchanged.

Tests cover aliases, distinct empty/equal/nested/cyclic arrays,
hostile payloads and mixed operands, left-to-right effects, source/AST/prepared,
Eval/Execute and a legacy mixed-type control. They also verify explicit experimental opt-in
and absence of VM fallback. A 41-test focused cohort (the new sixteen methods,
scalar semantics, direct array contracts and direct array reads) passes in
normal and optimized Python 3.12.

All direct compilation sites use the shared REPAIRS tuple: root/routines,
server/dual, source/configuration and their Eval/Execute profiles inherit this
operator repair. No constructor or receiver authority is added. Legacy codegen
is unchanged; experimental profiles without the explicit flag remain unchanged.

ValueTree integration and its two unchanged native assertions remain a separate
validation step. Comparisons without an exact primitive AST literal still call a small helper,
including variable-versus-variable scalar comparisons. Follow-up scalar-control
overhead measurements for the literal exclusion remain pending. No performance or complete native-parity pass is claimed.

## Exact Date boundary preservation

Before taking the array identity shortcut, exact BSLDate operands retain the
existing unknown-boundary rejection in both operand directions. The boundary
slot is captured when the Date class is defined; reading it does not call an
instance getter, a replaced class property or a patched `require_known` method.
Known dates remain unequal to arrays. Malformed non-Boolean boundary state is
rejected without truthiness callbacks. Non-array comparison paths are unchanged.

NULL and canonical Enum values have no analogous unknown-date precondition;
array comparisons retain the existing legacy distinct-type false/true result.
Foreign operands are not asked to run generic comparison callbacks. This does
not add scalar coercion or repair unrelated Map key semantics.

The 51-test Date module still reports two failures and fourteen errors, with
exactly the same failing subtests on parent 4248edbf. These pre-existing outcomes
are recorded separately, not counted as passing validation of this change.

## Static literal exclusion

For `=`/`<>`, an exact AST Literal whose value has exact type bool, int, Decimal,
str or NoneType leaves the old raw Python operator in place. Such an operand
cannot be an Array; mixed-array outcomes and original unknown-Date errors are
preserved. This is syntax-only: no variable inference, caching, group unwrapping
or custom/subclass literal admission. Nonliteral array comparisons continue to
use the bounded identity helpers. Generated-code and execution regressions
verify both directions, evaluation order/count, exact types and Date errors.

## Measured scalar cost, not a speedup claim

Two bounded frozen-source comparisons used seven alternating fresh-process
pairs with identical outputs and source hashes, verified package paths and
unchanged HEAD/tree/status before and after. The confirming pass used 10,000
loop iterations and five samples per case, with arithmetic and Boolean controls.

For the prepared variable/variable equality micro-cases, the identity helper
was slower in all seven pairs: median loops were approximately 3.010 to 4.401 ms
for `=` and 2.641 to 4.187 ms for `<>`. This is roughly 1.4–1.55 ms of added cost
per 10,000 iterations in these narrow loops, not a whole-engine or DB regression
estimate. Literal expressions use the original generated operator. Their timing
changes were not distinguishable from noisy controls; normal execute-path
numbers were also noisy. No speedup is claimed.

This is a correctness repair. It deliberately keeps the bounded helper rather
than introducing value-inference caches or complex temporary-based codegen to
hide that cost. The unchanged source-bound native Copy capture and array alias
assertions pass with explicit `python-direct`, as do the focused Date/boundary
checks on Python 3.12 and 3.10, both normally and with `-O`.

## Final integration checks

After integration on `b002f3666ca7c7e3eca63d927a37861830a86bb6`, all 2,074
broad direct/source tests pass normally and with `-O` in serial runs. The 49
focused boundary/Date/Copy tests also pass on Python 3.12 and 3.10 in both modes.
The unchanged two native Copy assertions were additionally run with explicit
`python-direct`. A separate 278-test direct tree/property-transfer cohort moves
from 17 errors / 7 failures to 17 errors / 5 failures: precisely those two Copy
methods are repaired; no other failing method is hidden or skipped.

An earlier parallel validation hit the native fixture's intentional fixed-name
collision guard. It was not counted as passing and no guard was weakened; the
final full broad runs were repeated without competing fixture owners.
