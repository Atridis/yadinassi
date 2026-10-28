# ValueTree Rows.Total / Итог: native32-aligned bounded runtime

[PR141 measurement run40768375140](https://github.com/Atridis/yadinassi/actions/runs/40768375140)
on `ef151a879b57e286882c3450c3ea965afa322a00`, tree
`082b86126110a95b50fc0ec268d8c6bc6417d56d`, yielded32 authenticated observations.
That run intentionally failed comparison with the absent runtime method. It is
**measurement evidence, not acceptance of this implementation**. Fresh native
and CI gates plus genuine whole138 with the new runtime remain required.

The source-bound finite record is
`TT: [144C99B0034222U2444EE4EEEEECC1134]` (final LF included in its SHA-256
`ec2a4cb29a7b9fc0e8114d1fb095f3c165b109d3dcefbe7a73dacbd9b47c25be`).
Complete native collections1023 SHA-256:
`ffb5c25587a158008d5e10ce3aae078d1d0f80f9623283253ee4f7a4bcdee3df`.
The old1022 native prefix was byte-exact to accepted main139. Only the unchanged
8 historical Map observations remain eligible for order comparison; no Total
exception, unknown or observer-failure tolerance was added.

## Measured behavior and bounded generalization

`Rows.Total(Column [, Recursive])` / `Строки.Итог(Колонка [, Рекурсивно])`
returns a Number or Undefined. Omitting Recursive and explicit False sum only
immediate rows. True, Number1 and String`"True"` recurse from that receiver,
not from the tree root. Explicit Undefined is rejected; it is not omission.
Other flag conversions are deliberately unsupported pending measurement.

Column selection accepts a case-insensitive name, a live column belonging to
this tree, or a finite Decimal position truncated toward zero **before** bounds
checking. Captured0,0.5,-0.5 all select column0. Boolean, Undefined, a foreign
column, missing/empty names and missing arguments fail. Other bounded Decimal
positions use that same method-local truncation rule as an algorithmic local
generalization; shared index rules are unchanged, especially Move's rejection
of negative-0.5. Case32 confirms mixed-case Russian method spelling and ASCII
column name folding, not all Unicode-name behavior.

Only the measured descriptor families are enabled:

- Untyped and Number+String: sum actual Number cells; captured strings, Boolean,
  Undefined and Null do not contribute. Other opaque untyped values are ignored
  without invoking hooks as a **local safety extension**, not extra native proof.
- Number-only: sum stored Number cells (measured1.25+2.5=3.75).
- String-only: bounded existing Number conversion (measured`"2"+"3"`→5 and
  `"2"+"x"`→2, invalid text contributing0).
- Boolean-only: True contributes1, False0 (measuredTrue/False/True→2).
- String+Boolean: Undefined (the measured two-row combination).

Other descriptor families/unions fail explicitly instead of inheriting a table
contract. Qualifier combinations and general text-conversion grammars are not
fully measured: arithmetic uses already-stored cells; any extension inherits
only the separately bounded existing converter, not a new claim of native parity.
Empty untyped and Number collections return0 after selector/flag validation.

## Exact arithmetic and local resource policy

The 29-digit value10000000000000000000000000000 plus1 remains exact; adding its
negative afterward yields1, and0.1+0.2 yields0.3. Only the existing GroupBy helper's
**exact addition** is reused, not GroupBy/Table type selection or conversion
policy. It runs inside a fresh Decimal Context after method-local validation,
so caller precision, exponent limits, rounding, flags and traps do not affect
or leak from the sum. Coefficient bounds are checked before tuple expansion.

Traversal is iterative, with at most100000 visited rows,1000000 visited cells,
4096 schema columns and tree depth256. There is an8000000 logical-work budget,
4096-digit numeric/conversion bounds, absolute adjusted exponent4096, and
16384 aggregate precision limit. Summation charges row-count×required precision
before arithmetic. These are **Yadinassi limits**, not platform limits.

Deleted/foreign/fabricated receivers and columns, malformed row ownership,
depth, duplicate references or cycles are rejected. Root/child receiver identity
checks concern this local runtime's internal graph, **not a new native wrapper
identity assertion**. No method writes cells, schema, order, parents, ownership,
indices or retained views, including on rejection. Nonrecursive mode does not
inspect descendant values. Structural checks also precede a String+Boolean
Undefined result.

## Regression and acceptance boundary

The32-probe BSL, codec, exact source pins, old1022 prefix, output count1023 and
report limits are unchanged. Tests bind the captured record and replay it under
both interpreter targets. Separate tests compare complete old1022 output before
and after method availability and exercise hostile Decimal contexts, bounded
resources, corruption and rejection without mutation. Synthetic observer tests
still model unavailable methods explicitly; their expected errors are not
rewritten as native answers. Runtime source inventory stays71, but its fingerprint
changes and requires fresh genuine whole138. Local parity is not remote native
acceptance, and no version bump is made.
