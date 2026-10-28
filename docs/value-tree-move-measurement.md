# ValueTree Rows.Move: compact measurement input

Status: measurement only. No native Move results or runtime implementation are
included. ValueTable.Move is not evidence for the separate tree API.

## Scope and record budget

The prior 1021 collections records and their helper bodies remain unchanged.
One final `TM: [payload]` record measures 32 independent fresh fixtures. The exact
source inverse reconstructs the accepted LoadColumn source SHA256
`ca23e52041022f2085c6cb7d4393a84834e75c69856c756b92e8531ad35c7c3e`;
this is source-only historical replay, never permission to accept output prefixes.

The payload is version `1`, followed by 32 fixed six-character observations:
`outcome + root order (3) + child order (2)`. Total payload: 193 ASCII characters;
complete message: **199 UTF-16 units**, or 200 UTF-8 bytes including its LF.
The old 3525-unit Load bound plus Move is 3724 of the existing 3800-unit allowance.
One additional message LF is reserved by the unchanged 4×character capture guard.
No truncation, cap increase, new report field, or relaxed old grammar is used.

Outcome `0` is an action exception, `1` statement success, and `2` expression
success returning Undefined (only case 32). Unexpected expression result types
are outside this initial observation domain and invalidate the record; they are
not assumed impossible. Error outcomes retain the complete post-action order,
including any partial reordering. Setup/schema/observer failures contain `!` and
must be rejected even if native and interpreter bytes are identical.

## Fixture and identity

Each normal case has roots A/B/C and two children D/E under A, with an untyped
Id column and distinct numeric cells 1–5. Order tokens come from exact retained
row references, not mutable Id values. Both saved and fresh Rows views must
have the exact collection type, count, Parent, unique retained rows, and equal
observable order. Rows wrapper equality is deliberately not required.

Every snapshot checks column collection and column identity, complete schema and
qualifiers, exact typed Id cells, row Owner/Parent and all leaf collections.
Moving A therefore observes preservation of its complete subtree. An independent
foreign singleton tree is checked unchanged before and after every action.
Empty and singleton cases are constructed empty, not cleared; their order fields
are `-----` and `A----`. Every case has a new fixture: actions cannot leak state
between observations.

## Fixed positional case matrix

Normal receiver is root Rows, selector retained B, offset +1 unless stated.

| Case | Action variation |
| --- | --- |
| 1 | Russian Сдвинуть(B, +1) |
| 2 | Mixed-case mOvE(index 1, -1) |
| 3 | B, zero offset |
| 4–5 | index 0/+2; index 2/-2 |
| 6–7 | index 0/-1; index 2/+1 |
| 8–9 | B, +10/-10 |
| 10–12 | index 0.5/+1; 1.9/-1; -0.5/+1 |
| 13–14 | index -1/+1; index 3/-1 |
| 15–18 | B, offsets 0.5, 1.9, -0.5, -1.9 |
| 19–21 | Undefined, Boolean True, String "1" selectors |
| 22–24 | Undefined, Boolean True, String "1" offsets |
| 25 | empty root, index 0/+1 |
| 26 | singleton root, index 0/+1 |
| 27 | A.Rows, retained D/+1 |
| 28 | A.Rows, index 1/-1 |
| 29 | A.Rows, root B/+1 (different collection) |
| 30 | root Rows, foreign tree row/+1 |
| 31 | Move(B), missing second argument |
| 32 | expression Evaluate("Rows.Move(Selector, Offset)") |

Deleted selectors, sibling-parent child selectors, zero/extra arity, wrong
receiver, Null and extreme resource-limit values are outside this small first
slice. Future implementation decisions must not invent answers for these cases.

## Acceptance boundary

The independent Move decoder requires exact 1022 whole-scenario records and the
sole final TM record. The unchanged Load decoder separately validates exactly
records 1–1021. Native and interpreter observations are both checked before
comparison; native export also checks Move independently of parity. Eight older
Map-order exceptions remain unchanged; Move never gains a semantic exception.

Synthetic tests establish grammar and observer behavior only, including action
errors after partial mutation, corruption rejection, foreign mutations and
unexpected expression results. A native measurement may validly mismatch the
currently unimplemented host Move. Inspect authenticated native observations
before implementing any behavior; publication of this measurement is not a
claim of runtime acceptance.
