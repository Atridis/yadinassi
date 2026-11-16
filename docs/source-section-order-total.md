# Source section scalar ordering and totals

The explicit section profile admits `Sort/Сортировать(specification)` and
`Total/Итог(field)`, operating only on the owned memory buffer.

Sort accepts a bounded comma-separated list of distinct scalar fields, each with
optional ASC/DESC or Возр/Убыв. Invalid directions, duplicate or unknown fields,
unassigned keys and reference/enum keys are rejected. All keys are validated
before mutation. Ordering delegates to the existing bounded ValueTable scalar
sort engine, including its explicit target-dependent tie order and limited string
collation alphabet. This reuse does not establish section native parity.

A successful reorder retains row handles and changes their LineNumber. Active
iteration is invalidated only when identity order changes. Failures preserve the
original order. No write, lifecycle callback or schema change occurs.

Total accepts only an explicitly declared Number field with every row assigned.
There is no Boolean/String coercion or invented default. The sum uses bounded
local Decimal precision derived from all addends, independent of ambient decimal
precision; empty input is zero. Values and whole-owner buffer budgets are checked
using the existing source codecs. The aggregate may exceed an individual field's
precision, but assigning it back still obeys that field's ordinary codec.
