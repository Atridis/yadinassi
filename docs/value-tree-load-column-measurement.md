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
objects and their element references are retained, including the separate foreign
selector tree. Unexpected collection replacement, schema/topology mutation or
unlisted value fails observation.

Column Name, Title, Width, type set, and all scalar type-qualifier fields are checked
against explicit immutable fixture values, before and after the action. The known
default qualifier values are also exercised by the existing values scenarios
`types.properties.description.default/scalars` and `types-extra.qualifiers.default`.
The new exact tree fixture must still pass its own native validation. Comparing a
mutable descriptor object to itself is not sufficient.

Identity calibration checks aliases versus distinct equal-valued Structure, Array,
FixedArray, and tree collections/rows. These checks must pass in the native run;
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
all original checks succeed. Otherwise it returns one finite stage below, without
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
| `G` | Root Rows repeated getter identity |
| `H` | Columns repeated getter identity |
| `I` | Child Rows repeated getter identity |
| `J` | Distinct root Rows identity |
| `K` | Distinct Columns identity |
| `L` | Distinct child Rows identity |
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
