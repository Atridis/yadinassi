# ValueTree Rows.FillValues / ЗаполнитьЗначения: standalone measurement

This is a measurement candidate, not an implementation or a claim of native
parity. The existing six ordinary integration sources and their outputs,
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

The standalone ASCII output has exactly 33 lines and 6017 bytes: one calibration
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
not runtime acceptance. Runtime alignment and its native parity gate follow only
after reviewing those observations.
