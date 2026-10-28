# ValueTree Rows.LoadColumn measurement checkpoint

Status: inputs and fail-closed observation only. Native results are not yet accepted;
Rows.LoadColumn is not implemented by this change. Synthetic method callbacks in
unit tests exercise observation branches, not expected 1C behavior.

## Scope

The 45 appended TL01–TL45 records leave the previous 976 collections records
unchanged. Main calls execute statements; TL34 alone observes expression use.
Tree and source are inspected after an action exception as well as success. TL37–40
also preserve the immediate post-action state before an independent mutation.

Normal fixtures have four columns and six retained rows. The typed fixture changes
Key to Number without adding a fifth column. Empty/no-column trees are constructed
empty, not cleared trees with retained deleted rows. Actual column/row collection
views and their element references are retained, including the separate foreign
selector tree. Rows views are checked independently for type, count, order, Parent
and exact retained row references; equal-content replacement views are permitted.
Columns collection identity checks remain in place. Unexpected schema/topology
mutation or an unlisted value fails observation.

Column Name, Title, Width, type set, and all scalar type-qualifier fields are checked
against explicit immutable fixture values, before and after the action. The known
default qualifier values are also exercised by the existing values scenarios
`types.properties.description.default/scalars` and `types-extra.qualifiers.default`.
The new exact tree fixture must still pass its own native validation. Comparing a
mutable descriptor object to itself is not sufficient.

Identity calibration checks aliases versus distinct equal-valued Structure, Array,
FixedArray, Columns collections and rows. Rows wrapper equality is not required;
retained and fresh Rows views instead satisfy the same read-only state predicates. These checks must pass in the native run;
passing host tests is not evidence of native LoadColumn behavior. Bidirectional
mutation witnesses are retained independently of the identity comparisons.

## Bounded record protocol

Each message is `TLnn: [payload]`, with eight framing characters. Payload starts
with six characters: version `1`, validated case baseline ID, action outcome,
mutation outcome, and a two-character expression result (`--` when not evaluated).

A snapshot has 59 characters: schema identity, topology identity, 24 two-character
cell values, source kind, source-container identity, source count, and three
padded two-character source values. Empty modes validate genuine emptiness before
padding absent rows. Scalar invalid sources still encode their actual values.
Source containers and Structure cell identities use separate domains.

Scalars distinguish Undefined, Null, Boolean, admitted exact integers and exact
strings. Structure cells admit exactly one case-sensitive property Mark with one
of three literal markers; an explicit bounded reference registry preserves aliases
across snapshots. Unknown type/value/shape has no successful generic fallback.
Scalar equality is typed; strings/property names use length and code-point checks,
not collation normalization. Registry allocation is deterministic and limited to60
Structure objects per case; at most58 are needed under the observation bound.

TL37–40 each add one separator and a second complete snapshot:

`45 × (8 + 6 + 59) + 4 × (1 + 59) = 3525` UTF-16 units.

That leaves275 units of the3800-unit available collections character budget.
The count becomes1021, while the existing4×character guard and all byte/report
caps remain unchanged. No output is truncated. A failed observer snapshot starts
with `!` and is never acceptable—even if native and host outputs match. Setup and
calibration failures remain distinct from action exceptions. An out-of-domain
native observation requires investigation and a separately justified bounded
schema change, not normalization or an increased cap.

## Case inventory

- TL01: base; root; selector Id; Array[6,7]; Russian ЗагрузитьКолонку statement.
- TL02: base; root; selector iD; Array[6,7]; English lOaDcOlUmN statement; combines method/name casefold.
- TL03: base; A.Rows; selector Id; Array[6,7]; child collection.
- TL04: base; A11.Rows; selector Id; Array[6,7]; empty leaf collection.
- TL05: empty; root; selector Id; Array[6,7]; independently constructed empty root.
- TL06: no-columns; root; selector 0; Array[6,7]; empty schema index.
- TL07: base; root; selector Id; Array[]; empty source.
- TL08: base; root; selector Id; Array[6]; short source.
- TL09: base; root; selector Id; Array[6,7,5]; long source.
- TL10: base; root; selector Id; FixedArray[6,7]; fixed source.
- TL11: base; root; selector 0; Array[6,7]; index zero.
- TL12: base; root; selector 1; Array[6,7]; index one.
- TL13: base; root; selector 0.5; Array[6,7]; fraction selector.
- TL14: base; root; selector 1.5; Array[6,7]; fraction selector.
- TL15: base; root; selector 1.9; Array[6,7]; fraction selector.
- TL16: base; root; selector -0.5; Array[6,7]; negative fraction selector.
- TL17: base; root; selector own Columns.Get(1); Array[6,7]; owned column selector.
- TL18: base; root; selector Missing; Array[6,7]; unknown selector nonempty.
- TL19: empty; root; selector Missing; Array[6,7]; unknown selector empty root.
- TL20: base; root; selector Missing; Array[]; unknown selector empty source.
- TL21: base; root; selector foreign Columns.Get(0); Array[6,7]; foreign column; full foreign schema/topology validation.
- TL22: base; root; selector -1; Array[6,7]; negative index.
- TL23: base; root; selector 4; Array[6,7]; out of range for four columns.
- TL24: base; root; selector Undefined; Array[6,7]; undefined selector.
- TL25: base; root; selector True; Array[6,7]; Boolean selector.
- TL26: base; root; selector Id; String bad; invalid source kind.
- TL27: base; root; selector Id; Number7; invalid source kind.
- TL28: base; root; selector Id; Undefined; invalid source kind.
- TL29: base; root; selector Id; Null; invalid source kind.
- TL30: base; root; selector Id; Structure(Mark=base); invalid source kind.
- TL31: base; root; selector none; Array[6,7] retained but not passed; LoadColumn() missing both arguments.
- TL32: base; root; selector Id; Array[6,7]; LoadColumn(Source, Id, True) extra argument.
- TL33: base; tree itself; selector Id; Array[6,7]; wrong receiver.
- TL34: base; root; selector Id; Array[6,7]; expression Evaluate; capture result and state.
- TL35: base; root; selector Key; Array[1,True]; typed scalar distinction.
- TL36: base; root; selector Key; Array[Undefined,Null]; nullish distinction.
- TL37: base; root; selector Key; Array[Structure(Mark=base),7]; two snapshots; Source[0].Mark=from-source.
- TL38: base; root; selector Key; Array[Structure(Mark=base),7]; two snapshots; A.Key.Mark=from-result.
- TL39: base; root; selector Key; Array[6,7]; two snapshots; Source.Delete(0).
- TL40: base; root; selector Key; Array[6,7]; two snapshots; Source[0]=5.
- TL41: typed; root; selector Key; Array[7,bad]; conversion/partial mutation.
- TL42: typed; root; selector Key; Array[bad,7]; conversion/partial mutation.
- TL43: typed; root; selector Key; Array[7,Undefined]; undefined conversion.
- TL44: typed; root; selector Key; Array[6,7,bad]; long typed source/extra-element validation.
- TL45: base; root; selector omitted; Array[6,7]; LoadColumn(Source) missing selector.

## Finite rejected calibration diagnostic

This revision identifies a failing calibration operation; it does not implement
LoadColumn or supply accepted native behavior. Calibration returns `-` only after
all current checks succeed (the reduced Rows predicates are specified below). Otherwise it returns one finite stage below, without
exception text or arbitrary object values. The rejected payload is
`1?C0<stage>-!` followed by 58 dots (65 characters). All 45 such complete messages
use 3285 UTF-16 units. Successful observations retain the 3525-unit bound, below
the unchanged 3800-unit allowance.

The strict decoder and artifact export gates still reject every diagnostic
failure, even when both sides match. A stage identifies the operation, not whether
the native cause was unsupported comparison, unequal identity, or another error.
Identity/schema checks must not be removed merely to obtain an accepted output.

A future auditor may reconstruct the finite all-45 stage candidates using an
authenticated unchanged 976-record prefix, but must require an exact native size
and SHA-256 match with server/client agreement. No match or ambiguous match is
inconclusive; matching a stage is not LoadColumn behavior acceptance.

| Stage | Operation |
| --- | --- |
| `0` | Reserved entry fallback |
| `1` | Construct Structure objects and alias |
| `2` | Structure alias identity |
| `3` | Distinct Structure identity |
| `4` | Construct Array objects and alias |
| `5` | Array alias identity |
| `6` | Distinct Array identity |
| `7` | Construct FixedArray objects and alias |
| `8` | FixedArray alias identity |
| `9` | Distinct FixedArray identity |
| `A` | Construct two trees |
| `B` | Retain root Rows |
| `C` | Retain Columns |
| `D` | Add first row |
| `E` | Add second row |
| `F` | Retain child Rows |
| `G` | Retained and fresh root Rows state consistency |
| `H` | Columns repeated getter identity |
| `I` | Retained and fresh child Rows state consistency |
| `J` | Known populated root and separate empty root state |
| `K` | Distinct Columns identity |
| `L` | Both known empty child views with their expected Parents |
| `M` | Row repeated getter identity |
| `N` | Distinct row identity |
| `O` | Construct scalar registry |
| `P` | Encode Number 1 |
| `Q` | Encode Boolean True |
| `R` | Encode String 1 |

### Rejected calibration reason in the finite report

The original diagnostic revision kept the stage only inside rejected output;
therefore its artifact gate correctly withheld the stage along with all raw
outputs. A failed run does not establish which calibration statement failed.

For the exact pinned collections source, the comparison now exposes a finite
`failure_kind` of `tree_load_calibration_0` through `tree_load_calibration_R`
only when the authenticated native capture has 1021 framed records and all 45
ordered `TL01`–`TL45` records are identical exact rejected-calibration packets
for that stage. Mixed stages, unknown codes, malformed framing, wrong counts or
source bindings retain `tree_load_observation_invalid`. The 976 preceding
records are framed, not newly accepted as native parity. Host-only failures
never produce a native calibration-stage reason.

This reuses the existing failure field, adds no report key and no runtime file,
and uses 23-character values shorter than the existing 29-character generic
failure. Status remains `error`, acceptance remains `rejected`, host comparison
fields remain null, and the six-output artifact is still withheld. The strict
observation decoder and native artifact acceptance rules are unchanged. These
reasons diagnose calibration only; they are not accepted LoadColumn behavior.

### Temporary fail-only Rows view experiment

Authenticated run `40674573926` on `e9fe3e53328da2336b179ea29f738c2ccbf1bbcc`
reported `tree_load_calibration_G`. This proves failure at the statement
`T.Rows <> RootRows`; it does **not** distinguish a true inequality result from
an exception while evaluating that statement, and proves no LoadColumn behavior.

The next temporary measurement therefore does not run LoadColumn at all. The
original calibration and action helper bodies remain byte-identical. A separate
experiment runs once and supplies a four-character result to a dedicated
fail-only wrapper for the existing 45 labels. Those 45 repetitions are framing,
**not 45 independent measurements**. The first 976 scenario messages are unchanged.

Each part has a fresh, independent disposable fixture:

1. Retain `Saved = T.Rows`, access Columns, add two rows through `T.Rows`, access
   the first row's Rows, then evaluate exactly `T.Rows <> Saved`. Setup ordering
   follows the original calibration A–F (including a separate unused Other tree).
2. Independently repeat that setup, assign `Alias = Saved`, then evaluate
   `Alias <> Saved`.
3. On a new tree with a Marker column and both counts initially zero,
   add through Saved and write marker 17. Through a fresh `T.Rows` getter check
   count 1 and read the numeric marker 17.
4. Independently start empty, add/write through fresh `T.Rows`, then check count
   and read marker through Saved.

For parts 1–2, T/F are the raw **inequality** result: T means the comparison
reported different, F means it did not. E means the measured comparison/read
raised. For parts 3–4, T/F describe the complete count/type/marker visibility
predicate; E means that measured add/write/read operation raised. Setup failure
is a separate hard-failure sentinel, never E or an omitted argument. Four
independent fixtures create six disposable trees in total because parts 1–2
retain the original unused Other-tree construction. No actual LoadColumn
fixture or previously emitted record is mutated.

Only one of the 81 four-trit vectors is returned. The exact packet is 65 ASCII
characters: `1?D0` + four T/F/E characters + `!` + 56 dots. The entire 45-message
suffix occupies 3285 UTF-16 units, below the unchanged 3525/3800 bounds. Unknown
values or setup failure produce a generic rejected packet, with no fall-through
to the original action helper. The report may expose `tree_rows_XXXX` (14 ASCII
characters) only for the pinned source, 1021 complete frames and 45 homogeneous,
correctly labelled packets. Malformed/mixed/unbound output remains generic.

All these reports remain error/rejected and nonexportable. Observed mutation
visibility, if obtained, would establish only these concrete shared-data
observables—not general wrapper identity, row ownership, or a replacement for
all schema/topology/retained-row invariants. Further observer changes require
separate review against the actual native result.

### Independent Columns experiment after the Rows result

Authenticated native run `40680283658` on `d87ccf2f9dc09c5608d439c7e0f6a46b86807ef9`
reported `tree_rows_TFTT`: the repeated Rows getter comparison reported different,
the variable-alias comparison did not, and both specific count/type/marker
visibility checks succeeded. This is one four-part experiment; it does not prove
general identity, ownership or LoadColumn semantics. The existing evidence is
preserved. The read-only Rows observer consistency adjustment described below is now
integrated; the diagnostic experiment remains available only as historical code.

Columns wrappers were not measured by that Rows experiment. A separate revision
therefore ran a similarly isolated **Columns-only** experiment, retaining
Columns before the two row additions and child-Rows access, as in the original
calibration's setup preceding H. Its independent parts are:

1. `T.Columns <> Saved` after that setup.
2. `Alias <> Saved` on a separate identical setup.
3. From initial count zero on both handles, add column `Marker` and write Width
   17 through Saved; through fresh Columns verify count 1, exact name code points,
   and numeric Width 17.
4. Independently add/write through fresh Columns and verify through Saved.

Again T/F are raw inequality results for parts 1–2 and explicit visibility
predicates for parts 3–4; E preserves operation exceptions, while setup errors
remain hard failures. A fresh fixture is used per part; four independent
fixtures create six trees because the original unused Other-tree construction
is retained in the two comparison setups. The experiment is computed once;
45 labels repeat its framing, not independent measurements.

That historical packet is `1?K0` + four T/F/E characters + `!` + 56 dots: still 65
ASCII characters and 3285 total message units. Only the pinned source with all
1021 frames and 45 correctly labelled homogeneous packets can expose the finite
`tree_cols_XXXX` reason. It remains rejected/nonexportable; the ordinary
LoadColumn action helper and calibration bodies were unchanged and uncalled by
that diagnostic route. That route is no longer active in the restored revision. Columns-element/row reference equality, schema metadata, qualifiers,
and owner/parent invariants are not inferred from these four observations.


### Restored action observations: reduced Rows claim

Authenticated native run `40685252053` on
`621afaf369fd4ee3c22a147219602912ec76d40b` reported `tree_cols_FFTT`:
repeated-getter and variable-alias inequality both returned false, and both
specific Add/Width-17 visibility predicates passed. This does not establish
column-element identity or general future aliasing. Original Columns calibration
H/K, column identities and all metadata/qualifier checks remain fail-closed.

The active suffix now calls `TreeLoadProbe(1)` through `TreeLoadProbe(45)` directly.
Neither diagnostic experiment is actively dispatched. The inactive Columns
definitions remain in the source; both experiment revisions are preserved by
exact source/history fixtures for replay. No LoadColumn runtime
implementation is added. Restored native action observations are still pending;
local synthetic callbacks are not accepted native semantics or merge readiness.

Rows calibration G/I/J/L no longer treats collection-wrapper equality as identity
evidence. Every retained root/child/foreign Rows view and every fresh view is checked
independently for the actual Rows type, count, order, Parent and the same immutable
row references. Row Owner/Parent/reference checks, cells, source state, schema and
column guards remain intact. Observations never mutate fixtures to test aliasing.
Partial action mutations are observed even when the action raises.

This deliberately proves only current observable consistency. Same-content copied
Rows collections may pass. In particular an empty root or foreign-root collection
from another tree can satisfy the same type/count-zero/Parent-Undefined predicates;
there is no observable backing-owner or future-aliasing guarantee. This limitation
is explicit and tested, not inferred away from the two native visibility checks.
Changed members/order/parents, replacement row objects, unknown values and wrong-type
duck-compatible containers remain rejected; allowed cell changes remain visible in
the complete encoded state. The 45 complete messages retain the 3525-unit bound
within the unchanged 3800-unit allowance and all prior export/acceptance guards.
