# ValueTree Rows.Move — bounded implementation, runtime acceptance pending

The 32 compact observations in native Linux 1C 8.3.27.1508
[run 40734394630, attempt 1](https://github.com/Atridis/yadinassi/actions/runs/40734394630)
were authenticated on measurement head `b5637894a3758de5f691f1ef3eafe94ef66cc3bb`
(tree `dad89282b854ed03d4d31b37cf3493423b182ca8`). Their complete 199-unit TM
message is retained as a literal in `tests/test_value_tree_move_native.py`.
The earlier 1021 native records were unchanged. That run failed host comparison
because Move was absent; it is observation evidence, **not runtime acceptance**.
Fresh runtime gates and native comparison remain required for this implementation.

## Implemented bounded behavior

`Rows.Move(row_or_index, offset)` / `Rows.Сдвинуть(...)` is a procedure on a row
collection, not the tree. It reorders only the receiver's immediate rows. A row
selector must belong to that exact collection; a numeric selector must be
nonnegative and within the receiver before truncation toward zero. Thus selector
0.5 selects index 0, but selector -0.5 is an error. Offset fractions truncate toward
zero independently: +/-0.5 is a no-op; +/-1.9 moves by +/-1.

The final destination must be in range. There is no wrap, clamp, append or partial
move on a validation error. Numeric/ownership/destination validation completes
before one in-place pop/insert, preserving saved views, row identity, cell objects,
Owner/Parent, complete subtrees, schema and the tree-wide insertion registry.
Expression use fails before the callback; the measured case 32 leaves order intact.

The native matrix observes 17 statement successes and 15 errors, including empty
and singleton offset+1, out-of-range destinations, Undefined arguments, foreign
collection/tree rows and missing second argument. See the
[exact 32-case inventory](value-tree-move-measurement.md).

## Conversions and explicitly local policy

The exact measured conversion witnesses are Boolean True and String "1", each
used separately as selector and offset. The implementation reuses the existing
strict standalone Number converter after exact-type gates, rather than
TypeDescription's Undefined/malformed-text-to-zero conversion. Undefined, Null,
unknown host objects and malformed/nonfinite text are rejected.

Other bounded valid numeric strings and Boolean False follow that existing Number
converter as **local extensions**, not additional native Move observations.
Likewise zero offset on a singleton, deleted/sibling row safety, zero/extra arity,
unknown host types, validation order when both arguments are invalid, and extreme
resource boundaries are local policies unless separately covered by the matrix.
Native error wording and exceptional allocation-failure rollback are not claimed.

Text conversion is limited to 4096 characters; numeric coefficients use the existing
4096-digit guard before tuple/integer expansion. Selector values are range-checked
before integer conversion; offset magnitude is bounded by receiver count before
integer conversion/addition. Existing whole-tree row limits remain unchanged.
These are Yadinassi resource limits, not asserted 1C platform limits. Temporary
Decimal conversion contexts do not leak malformed-input flags into callers.

The shared tree `_position`, ValueTable.Move, BSL measurement source, native
observer grammar, capture caps and previous LoadColumn evidence are unchanged.
Tests distinguish exact native 32 replay from additional local safety checks and
compare all earlier 1021 messages on both interpreter targets.
