# ValueTree.Columns.Move: measured Linux runtime

`Columns.Move(Column, Offset)` / `Колонки.Сдвинуть(Колонка, Смещение)` is a
procedure with two required arguments. Support targets **Linux 1C 8.3.27.1508**,
selected by interpreter configuration, independently of Python's host OS.
The Windows 1C target remains unmeasured and rejects the operation.

## Attributed evidence

Three authenticated server/client acquisitions provide 51 exact observations:

| Profile | Native run | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| CM28 | 41030064575 | 7480 | `2a691dda9e209583781d356a142f8866e057400bebfc6f83a5d39581d27b727c` |
| CB17 | 41034467262 | 4779 | `f19dee0a3f8ec4cb718902b2e259ee8c269ffd4d89803289dce73e5c62b150ad` |
| CT6 | 41037650691 | 1691 | `564cd7b8bd2d859471e6be65ab02e7f045294d77d97034160d5e78c9f7b54b2e` |

Each acquisition required positive EN/RU controls, exact server/client equality,
strict source/provenance validation and successful cleanup. The captures are
retained verbatim with their original run attribution, not regenerated expected
answers. Local replay covers the original observer, generated client module and
production host comparison. Fresh final runtime CI/native acceptance is still
required; local replay is not a fresh execution of native CB17 or CT6.

## Empirical model

A numeric selector is truncated toward zero and then checked against live
indices `0..Count-1` (so `-0.5` selects zero). A string selects a column by its
validated name. A same-tree column object selects its identity; an owned deleted
column has source index `-1`. Boolean selectors are rejected.

Offsets use bounded existing BSL Number conversion for Decimal, Boolean and
string values, then truncate toward zero. The destination is source index plus
the truncated offset, admitted in `0..Count`, inclusive. Destination `Count`
is a successful no-op, **not** append or clamp. An owned deleted column is also
a no-op for every admitted destination; invalid destinations reject. For three
remaining columns this explains deleted offsets +1/+2/+3/+4 succeeding and
0/-1/+5 rejecting, without special cases for those constants. Other admitted
sizes follow this empirical model; the observations do not prove every native
input or internal implementation.

Only the live column list is permuted. Column objects, row identity/topology,
parent/owner/depth, and column-to-cell associations remain unchanged. Both named
and positional values were observed independently in all 51 cases; their
agreement is an observed result, not normalization imposed by the decoder.
Measured argument errors and procedure-expression rejection leave snapshots
unchanged. This is not a claim of native transactionality outside these inputs.

## Local safety policy and exclusions

Exact receiver/owner/list/column types, identity uniqueness and unique bounded
names are checked without invoking arbitrary host equality or conversion hooks.
At most 4096 columns and the existing 8,000,000-unit local schema work budget are
admitted. Existing text and coefficient budgets apply before normalization or
conversion; the numeric magnitude is bounded before conversion to a Python
integer. These are Yadinassi safety limits, not measured platform limits.

No whole-tree or cell-value scan is needed for a pure schema permutation; row
and cell storage is neither traversed nor rewritten. Unsupported host objects,
malformed schema ownership, nonfinite or oversized numbers fail before mutation.
Arbitrary host mutation of row structures is not validated or repaired here.
`Columns.Clear` and deletion of the last column of a nonempty tree retain their
existing guards; no new lifetime behavior is inferred.

## Ongoing native coverage

The ordinary 28-case Columns.Move matrix lane remains required. The temporary
six-case exploratory matrix entry is retired after exact offline 28+17+6 replay;
this removes duplicate native execution, not semantic assertions. CB17 and CT6
source/contracts/closed registry routes remain immutable and manually
reproducible. Fill, Copy and Sort sources and generated modules are unchanged.
The retired probes' evidence continues to refer to their original runs above.
