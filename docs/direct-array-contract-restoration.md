# Direct Array contract restoration

This slice restores Array compatibility without selecting legacy execution for
the default path or excluding tests from the light tier.

## Separate representation and runtime failures

On `b97d5fced5f551a85e6ef9f42d196b0812a6104a`, the original
`test_array_defaults`, `test_array_delete_boundary`, and `test_array_gap_insert`
suite ran 40 tests with 117 errors and one failure (including subtests).
Most errors assumed a wrapper's `.items` on a direct native list.

The same assertions now run on both default `python-direct` and explicit
`compiled-strict`: exact list versus exact BSLArray, alias identity, atomicity,
recovery, snapshots, and complete serialization streams are checked. Host-only
checks are retained. Merely adapting the assertions produced 80 tests with one
error and one failure, exposing two genuine runtime gaps rather than hiding them:

* `Insert(0,)` treated an explicit omitted slot as Undefined.
* `New Array(fixedArray)` tried to interpret the fixed snapshot as a dimension.

Native collection omissions now reject before evaluating arguments, preserving
canonical legacy effect ordering. Host/source-member dispatch is unchanged.
Fixed snapshots recursively thaw to fresh native lists; repeated fixed branches
are independent copies, while other values retain identity. Exact tuple storage,
cycle, depth and cumulative slot/object budgets are checked before allocating the
result. FixedArray subclasses are explicitly unsupported, including nested ones.
No generic host-object access, implicit legacy fallback, or ownership exemption
was added.

Seven additional direct regressions cover source/AST/prepared routes without VM
block dispatch, nested aliasing, malformed snapshots, exact-type rejection,
resource boundaries, omitted-argument effects and late owner revocation.
The 87-test focused suite passed normally and under `-O` on Python 3.12 and
normally and under `-O` on Python 3.10. Integration on `d024351ef47776db3ca439f0d0e48ce77647fe3b`
passed all 1,413 tests in the complete `test_python_direct*.py` set plus the
three Array modules, normally and under `-O`. The adjacent fixed-map/fixed-array/
regex-service suite passed 26 tests. Independent final review found no blockers.

The unchanged multidimensional-array module was also checked: its errors fell
from 14 to 13, because the real fixed-snapshot copy case now passes. Its remaining
legacy representation/host-codec expectations were not skipped or rewritten in
this slice.

## Limits

This is a correctness change, not a performance claim or a full light-CI pass.
Other Array representation tests have not been rewritten wholesale. The separate
pre-existing numeric-dimension resource-limit issue is not claimed fixed here.
The `_MapEntry` TypeOf investigation is not part of this patch: admitting its type
alone exposes the next read-only-member boundary gap in collections.bsl.
