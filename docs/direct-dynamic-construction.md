# Bounded standalone dynamic construction

> Historical measurements below that name `compiled-strict` describe a retired
> backend. Current builds use only the direct BSL-to-Python generator.

The standalone direct backend supports functional `New(target, parameters)` with
native Array/Structure/Map constructors, its finite canonical service constructor
set, and UUID. It uses generated Python and existing bounded helpers, not the
legacy evaluator or a generic host factory registry. Source/configuration and
separate server compilation entries do not implicitly acquire this capability.
Standalone Eval/Execute and owned imported routines retain it.

Both expressions run exactly once, left to right, before validating the target.
Only exact strings or definition-time BSLType identities select a constructor.
There is no trimming, coercion, descriptor evaluation, or arbitrary callable
lookup. A non-array second value is ignored after its expression executes.
Exact native lists and canonical BSLArray storage are shallowly snapshotted;
FixedArray and list subclasses are not argument arrays. A 1,024-argument safety
limit is checked before snapshot allocation. Array dimensions retain their
existing bounds. These are Yadinassi limits, not asserted native 1C limits.

Live owner and canonical registration checks occur after argument effects.
Definition-time collection ABI checks precede reading BSLArray storage, and
BSLType selection never reads a host-replaced Enum.value descriptor. Prepared
code retains no constructor grant between executions.

## Limits and verification

Query, arbitrary registered factories, unimplemented finite factories, and
mutable Structure/Map copies from fixed counterparts remain unsupported. This
slice does not expand generic database or host-object authority.

The original 28-test DynamicNew module on parent
`43389e1ba1c057318c10f7661ddc41eb3a88db3d` had 60 errors on direct, while its
explicit compiled-strict control passed all 28 tests. The runtime implementation
alone left four unsupported errors and 16 subtest failures from one legacy
BSLArray representation assertion. That assertion now checks the exact native
list or legacy BSLArray type as appropriate, and all 28 tests run on both
backends. The combined 56 tests retain the four unsupported errors and have no
failures. No unsupported behavior was hidden by skipping or changing its expected
semantics.

A broader fixed cohort of 37 previously DynamicNew-failing methods gives 101
error records on the parent and 31 on the candidate, with no new failing method
identities. Of 26 now-passing methods, 25 are runtime repairs and one is the
backend-specific array representation assertion. Remaining errors include
unrelated static-constructor/member limitations exposed by those methods; this
is not a whole light-CI pass or a performance claim.

Ordinary copy/deepcopy of canonical argument arrays is supported before and after
lazy adapter initialization. The four slotless collection ABI classes declare
independent empty copyreg slot caches before their definition-time snapshots.
Replacement, deletion, nonempty mutation and unrelated hooks still fail closed;
copying does not silently invalidate an otherwise canonical array.

Final integrated production code passed 2,183 tests in both normal and optimized
Python 3.12 runs on a clean frozen checkout. The added slotted-subclass regression
was then checked with the complete 20-test adversarial suite separately. The
combined original 56-test dual-backend contract suite retains the same four
unsupported errors in normal and optimized mode; its 28 legacy tests pass.
