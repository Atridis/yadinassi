# Direct ValueTable omitted argument slots

A named direct table method previously received every omitted slot as
`Undefined`. Consequently, `Columns.Add(,,"Title")` failed its name validation
instead of supplying the empty-name default, while required holes such as
`Columns.Insert(,Touch())`, `FillValues(,Touch())` and `Get(,Touch())` executed
`Touch` before reporting the invalid call.

The existing table method boundary now receives a finite omission protocol for
exact canonical ValueTable, column collection and row receivers. Before argument
evaluation it rejects omitted slots outside the following optional positions
(zero based):

* Columns.Add: 0–3, defaults `""`, Undefined, `""`, 0.
* Columns.Insert: 1–4, the same defaults after the required index.
* Table.Copy: 0–1, Undefined.
* Table.CopyColumns: 0, Undefined.
* Table.FillValues: 1, Undefined; its value argument remains required.

Other table/row methods permit no holes. This is not early arity validation:
extra supplied arguments without an invalid hole keep their prior evaluation
behavior. Explicit Undefined is not converted to a default. Valid arguments
are evaluated once, left to right. Ordinary table calls without holes keep the
previous route unchanged. ValueList's existing optional-slot behavior is retained.

The frozen native collections `table.mutate.column-add-default` observation
records empty name/title and zero width. Partial omission semantics and rejection
order use the existing canonical runtime contract and regression tests, not a
new native capture. The full native suite is not claimed green.

Exact receiver identities are captured from definition-time table identities;
subclasses gain no protocol. Existing method resolution, live owner validation,
post-argument owner/lifetime checks and bounded-slice write restrictions remain
in place. No host receiver is newly admitted and no legacy evaluator is called.
Computed receivers with holes still fail before receiver effects. This slice
does not expand source-module dynamic callable omission support, fix table
property references or alter procedure metadata.
