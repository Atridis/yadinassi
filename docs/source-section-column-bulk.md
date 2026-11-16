# Bounded source section column operations

`UnloadColumn(name)` / `ВыгрузитьКолонку(имя)` returns a detached Array of the
explicitly assigned field values. Mutating the section or array does not change
the other container. Source-owned reference values preserve their identity.

`LoadColumn(array, name)` / `ЗагрузитьКолонку(массив, имя)` accepts an exact Array
whose length equals the current row count. `FillValues(value[, names])` /
`ЗаполнитьЗначения(значение[, имена])` fills explicitly named comma-separated
fields, or all declared fields when omitted/empty. Names are case-insensitive;
unknown, duplicate or whitespace-padded names are refused. Computed LineNumber
is not a writable field.

All target values use the existing exact section codec. There is no coercion,
partial-array mode or inferred default. The whole owner's section buffer is
bounded before any row is changed. Failures preserve old values and handles.
Successful updates preserve row identities and iteration structure; they do not
write the database or execute object handlers. An explicit document Write is
still required. Unassigned unrelated fields stay unassigned.

Existing owner, lifecycle, synchronous-server and safe-mode checks remain.
These are bounded source scratch operations, not complete native parity.
