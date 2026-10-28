# ValueTree Rows.Total / Итог: bounded measurement, not implementation

This change adds a native measurement only. `ValueTreeRows.Total` remains absent
from the interpreter until authenticated native results establish its contract.
The existing `ValueTable.Total` implementation is **not** evidence for trees.
No database, UI or recursive host traversal feature is added.

## Source and output preservation

The accepted pre-Total `collections.bsl` SHA-256 is
`a0212150d3d5d2a7252971aa8ba509d439ced04e85b5a157ff1148bf3eff4574`.
Removing precisely the new Total helper and final observation blocks must recover
those exact bytes, not a normalized or approximate equivalent. All prior 1022
records remain in their original order. A sole final `TT` record makes 1023.
The existing Load45 and Move32 observers remain independently mandatory; unknown
trailing records must not be ignored. Identical malformed native/interpreter
observations must never qualify as parity.

## Fixed 32-case matrix

The ordinary fixture has root rows valued 2 and 3; the first root has children
valued 5 and 11; the first child has a child valued 7. Thus root-local, complete
root-recursive, child-local and complete child-recursive sums would differ:
5, 28, 16 and 23. These are discriminators, **not claimed native answers**.

| Cases | Action / fixture |
| --- | --- |
| 1–3 | Root Rows; omitted, False and True recursive argument |
| 4–6 | Child Rows; omitted, False and True recursive argument |
| 7–8 | Empty untyped and Number-typed column |
| 9 | Number-typed values 1.25, 2.5 |
| 10–11 | String-typed values `"2","3"` and `"2","x"` |
| 12 | Boolean-typed True, False, True |
| 13 | Number+String column with 2 and `"3"` |
| 14 | String+Boolean column with `"2"` and True |
| 15 | Untyped 2, `"3"`, True, Undefined, Null |
| 16–20 | Column selector 0, 0.5, -0.5, True, Undefined |
| 21–25 | Own column, foreign column, missing name, empty name, omitted argument |
| 26–28 | Recursive argument Undefined, 1, `"True"` |
| 29 | Exact 29-digit value 10000000000000000000000000000 plus 1 |
| 30 | Same large value, then 1, then its negative; cancellation precision |
| 31 | Exact decimal 0.1 plus 0.2 |
| 32 | Mixed-case Russian method alias `иТоГ` and ASCII column-name `n` for `N` |

This does not cover all selector/flag conversions, deleted columns/receivers,
all unions or numeric magnitudes. In particular, case32 does not establish
Cyrillic column-name folding. No unmeasured behavior should be documented as
platform parity.

## Finite outcome codec

Payload: ASCII version `1` followed by 32 one-character observations. Its exact
length is 33 bytes. `TT: [` + payload + `]` is **39 UTF-16 units**, or 40 ASCII
bytes with the final LF. Executing the real managed-client adapter measured the
old1022 messages at 261827 UTF-16 units, not the earlier estimated76-unit spare
margin. With count1023 the unchanged capture bound is
`floor((1048576-1023)/4) = 261888`; the valid Total extension uses261866, leaving
**22 measured units**. An initial71-unit codec actually exceeded this bound by10
and was rejected. Its failed proof is retained, not presented as a passing gate.
No limits were increased.

Outcome `E` denotes an action exception, `U` Undefined, `L` Null. Numeric symbols
`0`–`9`,`A`–`C` index the exact decimal codebook in
`scripts/native_1c_tree_total_contract.py`. Ordinary cases share13 numeric
alternatives; cases9 and29–31 have dedicated smaller codebooks. Numbers are
compared as exact Number literals, never formatted to locale-dependent text.
Unexpected values/types and encoder exceptions produce `!`, which is rejected
as a diagnostic observation failure. A rejected unknown is not a native answer
and is not silently mapped to a likely expected result.

A valid outcome is returned **only after both independent invariant checks
succeed**. Reserved invalid symbols distinguish `P` (pre-check error), `Q`
(precondition mismatch), `R` (post-check error), `T` (post-check mismatch); their
fixed position identifies the case. They do not overlap any valid outcome. An
invalid invariant replaces the action outcome, including when the action threw;
the action result is intentionally not captured in that invalid observation.
The observer checks retained row identities, local order, cell types and exact
values, Owner/Parent, saved/current Rows views, column identities and saved
Columns collections, schema types and qualifiers, and the empty foreign tree.
Rows wrapper equality is deliberately not used. Observed mutation or an
observer error is invalid for this read-only measurement contract; this does
not assume in advance that native Total is nonmutating. Post-checks also run
when the action throws. Encoder failures are outside the action catch and cannot
be mistaken for native action exceptions.

## Evidence gates

Synthetic tests validate the observer/codec and are not native semantic evidence.
The native capture must be source-bound, decoded and validated before deciding
whether to implement any case. An unknown code/value needs a focused diagnostic,
not widening the answer domain after the fact without reviewed source changes.

The new distinct Total contract enters the trusted runtime source inventory
(current baseline70 → candidate71); this requires exact new provenance and a
fresh genuine whole138 verification before publication/native acceptance.
The unchanged limits remain: stage report8192 bytes, public report32768 bytes,
and raw async-adapter source294912 bytes, including physical CRLF checkouts.
The current candidate must prove serializer worst cases and exact historical
source inverses independently; an earlier main result is not that proof.

### Local bounds proved for this measurement candidate

The real managed-client adapter admits1023 messages at261866/261888 UTF-16 units.
The strongest complete preprocessor/runtime report envelope with **71 actual
runtime sources** is8185/8192 stage bytes (7 spare),32533/32768 public summary
bytes (235 spare), and15090/32768 provenance bytes. Async-only partition figures
7984/32161 are not substitutes for that stronger envelope. Physical CRLF
`full_suite.py` is292285/294912 raw bytes, leaving2627;45 standalone Python
comments were removed with AST identity verified, without changing a cap.
These are local gate results, independently repeated on physical-CRLF sources;
they do not establish native Total semantics or replace genuine whole138 proof.
