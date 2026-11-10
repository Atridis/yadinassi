# Independent periodic information registers

This is a bounded local persistence and query contract, not a claim of native
method parity. Independent registers may explicitly declare `WithinSecond`,
`Day`, `Month`, `Quarter`, or `Year` periodicity. Recorder-subordinate registers,
posting, movements and automatic migrations remain unsupported.

## Storage and identity

A newly created configuration containing a periodic register uses SQLite v9.
Existing v1–v8 files retain their format and semantics. A v8 file cannot admit a
periodic schema by changing its stored definition. Nonperiodic-only new files
still use v8. v9 may combine periodic and nonperiodic registers, documents and
catalogs, retaining separate schemas and receipt domains.

`Period` is a standard Date field before the declared dimensions. It is not a
user-defined dimension. Its metadata identity is derived deterministically from
the register identity. The persisted key consists of normalized Period followed
by the declared typed dimensions. Nonperiodic keys and schema serialization are
unchanged. Metadata `Periodicity` exposes the admitted metadata spelling.

Assignment normalizes Period to the beginning of the declared second, day,
month, calendar quarter, or year. Normalization is independent of local time
zones. Two values in the same bucket identify the same record; insertion must
not silently overwrite an existing key. Reading a selected record freezes its
whole key, including Period, until `Clear()`.

## Explicit application execution remains separate

Periodicity does not activate stored modules. The separate CommonModules runtime
requires its existing explicit opt-in, canonical source reimport and startup
schema comparison. The comparison includes the register periodicity, dimensions
and generated Period identity. A caller cannot change a schema from nonperiodic
to periodic while retaining different canonical XML. Privileged modules, reuse,
SessionModule and unsupported object behavior retain their existing refusals.

## Record buffers and selection

RecordManager `Read`, `Write`, `Delete`, `Selected` and receipt recovery retain
the independent register contract. Set `Period` alongside dimensions. A missing
`Read` preserves the selected period/dimensions and resets resource defaults.

For periodic managers:

- `Get(Period, Dimensions)` reads the exact normalized bucket and complete
  dimension key. An absent key returns resource/attribute defaults.
- `Select(Start, End[, Dimensions])` returns rows within inclusive whole-second
  boundaries. Bounds are not rounded to a storage bucket. Reversed bounds fail.
- `GetLast(Moment, Dimensions)` returns resource/attribute values from the latest
  period at or before Moment for a complete dimension key.
- `GetFirst(Moment, Dimensions)` selects the earliest period at or after Moment.
- `SliceLast(Moment[, Dimensions])` and `SliceFirst(Moment[, Dimensions])` return
  a ValueTable with Period, dimensions, resources and attributes. One row is
  selected per exact typed dimension tuple. No synthetic missing rows are made.

Slice/range boundaries must be known whole-second Dates. Fractional or boundary
states are rejected rather than silently altered. Select/slice results are
limited to 1000 rows; overflow is explicit. Source validation is bounded at
10000 rows / 16 MiB, including rows eliminated by the requested boundary.

RecordSet additionally exposes `Filter.Period`. Its value is normalized like a
record Period. A filtered replacement with that filter affects only that bucket
and the selected dimensions. Without a period filter it deliberately covers all
periods in the dimension scope. The existing requirement to `Read()` before an
unfiltered replacement remains. Revisions, frozen write intents, atomic scopes
and uncertain-commit receipt recovery are shared with the nonperiodic port.

## Filter order and Query virtual sources

Manager dimension filters are applied **before** selecting an edge. They accept
only declared dimensions, not resource conditions. `Select` bounds constrain the
period directly. Query admits:

```bsl
Q = New Query("SELECT Item, Period, Price FROM InformationRegister.Prices.SliceLast(&At) WHERE Enabled=TRUE ORDER BY Item");
Q.SetParameter("At", Date(2024, 1, 2));
Result = Q.Execute().Unload();
```

The virtual-source argument is one Date parameter. Arbitrary source expressions,
resource predicates inside source parentheses, optional omitted boundaries and
extra source arguments remain unsupported. Russian source names
`РегистрСведений`, `СрезПоследних`, `СрезПервых` and field `Период` are admitted.

The slice is computed first; Query `WHERE` is applied **afterwards**. If the latest
row has Enabled=False, `WHERE Enabled=TRUE` removes that dimension tuple. It does
not select an older enabled row. This ordering also holds in JOIN, UNION,
aggregate and temporary-table packages. All sources use the same owned read
snapshot. Validation and resource budgets account for historical source rows,
not just the smaller slice or projected columns.

See [the executable example](../examples/periodic-register-prices.bsl).
