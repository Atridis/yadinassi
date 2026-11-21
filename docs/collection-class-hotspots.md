# Collection class work, separate from direct-AST dispatch

## Reproducible evidence

Untimed `sys.setprofile` counters on 365c3c6f, prepared benchmark route,
512 rows/items, one warmed execution, setup and validation outside the capture:

|case|raw Python calls|class calls|AST calls|
|---|---:|---:|---:|
|ValueList build/scan|514|68,653|50,844|
|ValueTable build/scan|514|20,544|69,592|

The raw baseline constructs dictionaries and sums Decimal fields. It does not
implement item identity, owner lifetime, mutable schema, BSL index conversions,
readonly item replacement or transactional indexed mutation. It is a useful
lower bound, not a claim of identical capabilities. Counts are not wall time.

ValueList performs 60,928 generator resumptions for 512 stored numbers: 119 per
number, searching the global exact-type registry. This is O(items * registered
families), not O(items squared). Decimal is near the end of the registry.
This whole repeated classification search can be removed: the canonical type
registry already owns an integer-identity index retaining each exact type.
No value/content result is cached. Finite-number, digit/text and collection
mutation checks remain per operation. Replacing the private registry retains
the prior live linear semantics on that noncanonical path. This does not grant
additional direct-AST receiver authority.

## What should and should not be carried into a simpler design

* Separate immutable type classification from mutable value validation. Do not
  rebuild classification by traversing every unrelated runtime type per value.
* Keep storage mutation as a small explicit primitive. ValueTable.Add currently
  calls Insert with Decimal(len(rows)), which immediately converts that internal
  position back to an integer. Append and user-facing index conversion are
  different operations and should not share that round trip.
* Treat indexes as an optional storage observer. A table with no indexes still
  enters index budget and key-planning machinery, including 1,024 empty unit
  sums in this 512-row build/scan. A no-index mutation path should not manufacture
  index plans; indexed mutations must retain atomic preflight and rollback.
* Resolve field names through a schema-owned identity map rather than scanning
  all columns and recasefolding each name on every access (1,024 lookups here).
  This needs a real schema mutation contract for rename/add/delete/reorder and
  retained rows. A cached lookup over public mutable lists is not sufficient.
* Preserve observable live item/row identity. Replacing items with anonymous
  scalar list elements would invalidate GetID, references and detached-item
  semantics. A wholesale raw-list rewrite is not an equivalent implementation.

The three ValueTable changes form a coherent storage/schema redesign, not a
reason to bypass corruption or owner checks. They require dedicated native
index/schema mutation and failure-atomicity tests before timing or integration.

## AST is a different bottleneck

The AST benchmark already uses direct collection storage operations rather than
calling ValueList._value for each Add. Its 512-item loop makes 3,079 direct
boundary checks and 3,080 transaction checks; the table makes 4,109 and 4,110.
Context stack/local/database property reads dominate Python call counts there.
Consequently, faster class validation must not be advertised as an AST speedup.
Sharing a minimal storage primitive is preferable to carrying two full class
implementations, but callback/checkpoint and revocation rules still apply.
Removing these checks needs its own exact authority contract and paired wall
measurements, not inference from their call counts.

## Candidate evidence

With the exact identity index, 512-item class Python calls fall from 68,653 to
7,725; C calls change from 8,765 to 9,277. AST remains exactly 50,844 Python and
40,340 C calls. This confirms removal of the repeated registry traversal, not
relocation into an unmeasured AST operation.

Seven alternating fresh-process baseline/candidate pairs, 16 warmed executions
per sample, same 512-item prepared benchmark and exact result/collection checks:
ValueList classes median 5.571 ms to 2.631 ms, candidate faster in all seven pairs.
The target normalized to the raw baseline also improves in all seven pairs.
Controls were noisy: list raw 0.136 to 0.172 ms, AST 10.240 to 13.037 ms;
unchanged table classes 5.906 to 7.023 ms. Thus this supports the targeted class
improvement, not a precise universal speedup and not an AST performance claim.
No profiler was attached during timing. Timing windows were coordinated.

42 focused tests pass on Python 3.12 and Python 3.10 -O. The broader sort suite
has the same two failing identities/messages on baseline and candidate: native
observations hit the existing unsupported constructor, and an unsupported-value
case raises before its expected catch point. Neither expectation was changed.
