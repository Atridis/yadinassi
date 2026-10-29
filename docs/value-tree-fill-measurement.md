# ValueTree FillValues: absent-method regression and API controls

The initial measurement tested a mistaken API assumption. FillValues belongs to
ValueTable, not ValueTree or ValueTreeRowCollection. No corresponding tree runtime
method is implemented or planned. The added native controls remain pending. The existing six ordinary integration sources and their outputs,
including all 1023 collections records, remain unchanged. The separate bounded
tree profile carries this source so later tree operations do not have to discard
observer detail to fit the almost-full ordinary collections capture.

## Fixed 32-case matrix

Every case uses a fresh fixture. It retains six row objects: two roots, one
child below the second root, two children below the first root, and one grandchild
below its first child. The four columns are Id, Key, Group and Mark. Values and
row identities distinguish every row and every hierarchy level. An independent
empty foreign tree is retained too.

| Cases | Action |
| --- | --- |
| 1–2 | Root collection, omitted columns or Key only |
| 3–5 | First root's child collection, omitted columns or Key; grandchild collection, Key |
| 6–7 | Empty tree with columns; empty tree without columns |
| 8–9 | Empty column selector; whitespace around Key and Group |
| 10–12 | Missing; Key,Missing; Missing,Key, exposing partial writes and validation order |
| 13–15 | Key,Group; duplicate Key; trailing comma |
| 16–20 | Numeric selector; own column object; foreign column object; Undefined; Array |
| 21–24 | Missing required argument; excess third argument; expression call; mixed-case Russian method and ASCII column |
| 25–28 | Untyped Key assigned string, Undefined, Null or Boolean |
| 29–30 | Number-typed Key assigned numeric and nonnumeric strings |
| 31 | Mutable Structure assigned to Key, then its source property mutated |
| 32 | Number-typed Key assigned Boolean |

The ordinary fill value is Number 4. This matrix does not establish behavior for
String/Boolean-typed destinations, deleted rows/columns, arbitrary qualifier
limits, other unions or every malformed column selector. The expression case
observes whether the action is accepted and its side effects, not a returned
value. No default recursion behavior is assumed.

## Independent observation contract

The original standalone ASCII output has exactly 33 lines and 6017 bytes: one calibration
line followed by TF-1 through TF-32 in exact order. Each case has a 178-character
payload: action status S or E and three 59-character snapshots (before action,
after action, after explicit source mutation for case31). For other cases the
last two snapshots must be identical. A partial write followed by an exception
is recorded as E with the actual changed-cell state, not discarded.

Each snapshot independently checks schema identities, names, titles, widths,
type description and qualifiers; all retained row identities and local order;
Owner and Parent links; saved and freshly retrieved Rows views; retained Columns
collections; and the foreign tree. Rows wrapper identity is deliberately not
assumed. All 24 cells are recorded with a closed, type-sensitive codec. Mutable
Structure identities use a retained reference registry. The case31 source's
mutation discriminates shared references from equal-but-distinct copies.

The fixture's pre-state is checked against an independently constructed literal
baseline before invoking the action, and checked again by the Python contract.
The fixture/encoder failure codes P, B, Q and R are invalid observations, never
native action exceptions. Unknown cell values, broken invariants, malformed
records, duplicate/missing/reordered cases and bad calibration fail closed.
The finite cell codec intentionally rejects values outside its published domain;
such a result requires investigation rather than being turned into an expected
answer.

The observer mechanics are derived from the accepted LoadColumn observer on
main 2df9158edcdc460db235db546185188b410bb3de and namespaced TreeFill. The Boolean
source tag is added explicitly. The existing collection source is not changed.

## Gates

Local synthetic tests prove observer discrimination only: all32 unavailable
methods, partial writes with success versus exception, malformed outputs,
non-action structural corruption, shared versus copied structures, and encoder
failures. They are not native semantic evidence.

The separate profile must bind this exact source, contract, runtime and adapter,
run real managed 1C, and validate this closed contract before comparing with the
interpreter. A native measurement/interpreter mismatch is a measurement result,
not runtime acceptance. Any runtime alignment requires an actual documented API and reviewed native
observations; this absent-method regression does not authorize adding a method.

## Negative32 result and API-membership controls

Native run40874212976 on PR145 source head3441005 produced valid6017-byte output
SHA256 `e968638370962bbd51993f3757756e58cf6edb00fbe61fb37e4420b90c368f63`:
all32 attempted Rows.FillValues actions threw, without changing tree cells.
The profile transport and observer passed; this is **not implementation of
FillValues**. Those observations alone do not distinguish an unavailable method
from inappropriate invocation. They remain attributed to the original source
SHA256 `47ee0383ac5a9db0bf9d4132b78f0ca40eb46712b4152654feec776ce38e22df`.

An additive API-control extension preserves the exact original source when its
new helper block and final message are removed. Its first33 output records remain
byte-identical. One additional TF-A record produces34 lines and6107 bytes total,
within the unchanged8192-byte profile cap. The source/module hashes and counts
change together; this is a new native measurement, not a relabeling of run40874212976.

The16 controls use a fresh tree with one root and one child, plus a separate
one-row ValueTable:

1. Rows.Count, Rows.Количество and Rows.Get establish working tree receivers.
2. ValueTable.FillValues and ValueTable.ЗаполнитьЗначения are positive fill controls.
3. ValueTree and its Rows each receive direct FillValues and ЗаполнитьЗначения calls.
4. Each of those three receiver types receives a deliberately nonexistent method.
5. ValueTable.FillValues and Rows.Get are invoked without required arguments.
6. Rows.LoadColumn and Rows.ЗагрузитьКолонку establish working mutating tree methods.

Each control reports five finite characters: S(success), M(missing-method message
category), A(missing-argument message category), or O(other exception); a bounded
return-value code; and root/child/table cell values. Structural identity, shape,
parent and owner relationships, column names and input-array preservation are
checked independently after the action, including on exceptions. Observer failures
are invalid records, not action exceptions.

Exception descriptions are examined only inside the fixture and reduced to fixed
M/A/O categories. Raw exception text, paths, arbitrary messages and stack traces
are never exported. These categories recognize specified Russian/host phrases;
an unrecognized wording is O, not a guessed diagnosis. The deliberately missing
method and wrong-argument controls calibrate those categories on the real platform.
A membership conclusion requires their results and the positive controls, not
merely a passing transport job. Host synthetic expectations are not native results.
No new runtime method is added by this extension.

## Primary API evidence

The official [EDT2026.2 syntax-help bundle](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar),
SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`,
contains complete RU/EN method inventories in
`nl/{ru,en}/html/SyntaxHelperContext/objects/catalog234/catalog264/ValueTree.html`,
`ValueTreeRowCollection.html` and `ValueTreeRow.html`. Neither the tree nor its
rows exposes FillValues. ValueTree.Copy and ValueTreeRowCollection.Sort are the
actual remaining tree operations of interest. The FillValues entry is under
`catalog234/catalog236/ValueTable/methods/FillValues600.html`.
The official [8.3.27 overlay](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_v8_3_27_1.0.400.v202609220822.jar),
SHA256 `c140925e80ad3a64b528b70a362ff6709f43e65b3e39e9736bad0d5e482d79f6`,
has no replacement for these entries. No bundled vendor documentation is
republished here. The additional native controls verify exception categories and
working receiver/alias controls on the pinned executable, independently of the docs.

## API-control observer context correction

Run40880375728 on head `de298f0b9dafb88bb57d8530585d5b5298e06a9e`, source
`43b06200bb0830ca47fb6ab38353e41dae71a10488a34d83cb5d8eb8ce53863b`,
produced a valid6107-byte native capture, SHA256
`bc92ed9b13a2e01ac8150a90cffc52bc0496723cf4ca71480df82e386e6cd3c9`.
The original6017-byte prefix was unchanged. Positive controls1–5 and15–16
succeeded; exception controls6–14 yielded category O, while the interpreter
classified them M/A. Thus the measurement was valid but parity was not accepted.

That source retrieved ErrorDescription inside a classifier after entering a new
nested Try in the action's exception handler. The corrected observer captures the
private String immediately in the original exception handler, before any nested
Try or classifier call, and passes that value to the classifier. Category rules,
output grammar, structural guards and raw-error nondisclosure are unchanged.
A direct source-order regression and a classifier test that forbids rereading
ErrorDescription protect this boundary.

This is an observer-context correction awaiting its own source-bound native run.
It is not a verified fix or general compatibility claim about the interpreter's
nested error scope. A possible ErrorDescription scope discrepancy remains a
separate investigation; the historical O observations are not rewritten as M/A.
