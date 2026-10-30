# ValueTree Columns.Move: standalone observer preparation

This observer adds no runtime method, shared fixture or native result. Its
standalone V2 preparation preserved every pre-existing Sort runtime V3 source.
The subsequent fixed profile integration is described in
[value-tree-columns-move-profile.md](value-tree-columns-move-profile.md).
The actual current interpreter reports missing method in all 28 cases; that is
valid acquisition-shaped output, **not** availability or parity evidence.

## Primary API evidence

The official [EDT 2026.2 SyntaxHelper bundle](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar)
SHA256 `a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`
contains the complete EN/RU ValueTreeColumnCollection inventory and
`nl/{en,ru}/html/SyntaxHelperContext/objects/catalog234/catalog264/ValueTreeColumnCollection/methods/Move691.html`.
EN entry SHA256 `ee47ab3f966291ecce0502a9c158af1b931fa5c3830c250a649183d6569383b1`;
RU `01a0dbefaea6fe01e7614ee98a04140620fb74cb54f9794f5971ff0ed6755607`.
The official [8.3.27 overlay](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_v8_3_27_1.0.400.v202609220822.jar)
SHA256 `c140925e80ad3a64b528b70a362ff6709f43e65b3e39e9736bad0d5e482d79f6`
contains no replacement entries for this collection. Both archive hashes were
freshly verified during preparation; vendor documentation is not republished.

`Move(Column, Offset)` / `Сдвинуть(Колонка, Смещение)` has two required
parameters: Number or ValueTreeColumn selector, and Number offset. Direction is
toward the end for positive offsets, toward the beginning for negative offsets.
Server and thick-client contexts are documented. Fractional conversion, errors,
name selectors, expression use and precise boundary behavior are measured here,
not inferred from Table.Columns.Move or Tree.Rows.Move.

## Fresh fixtures and cases

Each case creates three untyped columns Key/Secondary/Tag, distinct titles and
widths, and five rows: two roots, two children beneath the first root, and one
grandchild beneath its first child. Preorder row i has numeric cells i+1,
(i+3)%9 and (i+6)%9. Case 17 has no rows or columns; case 18 has one column and
five rows. A temporary P column is deleted before snapshots to supply a stale
selector; an independently created foreign column supplies case 15. Foreign
receiver contents are not part of this initial observation domain.

| Case | Call, normally on T.Columns |
|---|---|
| 1 | EN Move(1, 1), required availability control |
| 2 | RU Сдвинуть(retained Secondary column, 1), required control |
| 3 | retained column, 0 |
| 4–5 | 0,+2 / 2,-2 |
| 6–7 | 0,-1 / 2,+1 |
| 8–9 | 1.9,-1 / -0.5,+1 |
| 10–11 | retained column,+1.9 / retained column,-0.5 |
| 12 | string Secondary,+1 |
| 13–14 | -1,+1 / 3,-1 |
| 15–16 | foreign / deleted column,+1 |
| 17–18 | empty / singleton column collection,0,+1 |
| 19–20 | retained column,string 1 / Undefined offset |
| 21–22 | missing offset / extra third argument |
| 23 | expression Move(1,1), dynamically executed |
| 24–25 | Boolean / Undefined selector,+1 |
| 26 | retained column,Boolean offset |
| 27 | retained column,1000000 offset |
| 28 | no arguments |

## Observations, not assumed semantics

Calibration independently checks primitive encoding, distinct object identities,
column collection identity and hierarchy. Every case records before and after
snapshots with one shared identity registry. Schema order includes actual column
identities, names, titles, width, type and qualifiers. Rows encode actual identity,
parent, tree owner, level, child count and positional cells and an independent sequence resolved by each column name.
Their values need not agree: discrepancies remain observable, not normalized or
converted into observer failures. Rows collection owners are structural labels,
not comparisons between wrappers that may be unequal.

Statuses S/M/A/O represent statement success, missing method, coarse arity-like
error, and other action error. E is allowed only for case 23 when expression use
returns Undefined. Other successful expression result types are outside this
initial observer domain and produce a rejected observer failure. The Result
variable is initialized before dynamic execution so no scope accident masks it.
Original exception descriptions are captured before any helper runs; descriptions
are never exported. XB/XO and failed calibration are never valid evidence.

The decoder checks finite syntax and coherent per-snapshot hierarchy, not a
presumed successful permutation or rollback. Changed cells, schema/order and new
valid column/row identities remain observable after success or error. Snapshots
are limited to three columns and five rows (zero rows in case 17), at most 62
registry identities and the documented scalar vocabulary. Other observations
fail closed; they must be investigated, never normalized into expected output.
`require_available` requires both cases 1 and 2 to have S status. Identical M
records cannot pass this gate. Real server/client exact parity is still required
when subsequently integrated.

## Budgets and staged integration gate

There are 29 messages including CM-C1 calibration. For c columns and n rows a
snapshot is `5 + 13*c + n*(6 + 4*c)` bytes. Constructive coherent maximum capture
is **7690 / 8192** bytes. A proposed fixed `tree-columns-move-v1` completed marker
is 7874 compact bytes; the tested escaped/spaced/BOM upper form is
**7999 / 16384**. These are standalone wire proofs, not approval of an unbuilt
profile integration. The actual current missing-method capture is 7480 bytes.

The integration gate requires exact generated server/client module sizes and complete
stage/native/host/provenance/transport envelopes under existing caps. Leave
full_suite.py unchanged: 289493 LF / 294075 CRLF bytes, only 837 bytes below its
294912 source cap. Keep all existing source hashes, modules and historical pins;
use fixed lazy profile dispatch and a literal matrix entry, no dynamic paths or
arbitrary profile inputs. New integration must independently reject unknown or
duplicate profiles and mixed artifacts. No cap increase is proposed.

Synthetic tests distinguish no-op, bounded and wrapping models, observe partial
mutation before error and replacement column identity, and exercise expression,
post-action named/positional divergence, calibration and observer failure paths under normal Python and -O. These are
observer tests, never substitute native answers. Clear and last-column deletion
remain separate lifetime features with their existing guards untouched.
