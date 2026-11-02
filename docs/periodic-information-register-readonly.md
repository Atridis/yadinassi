# Bounded Second-periodic InformationRegister reads

Native measurement `41380811903` (source `0d2125`, tree `c5b012be`) accepted
both generated metadata identities and both field orders, empty/filled states,
and client/server. Independent/Second CONFIG is literal mode 5; the exact physical
profile has `_PERIOD DT` followed by the six measured fields. Raw Period values
are correlated with the independent setup query; they are not inferred by adding
a guessed date width to an arbitrary table. Every active key is unique across
Period plus both dimensions. Nonperiodic reading remains a separate exact profile.

## Read workflow

- `GetFirst(Date, completeKey)` / `GetLast(Date, completeKey)` return a fresh
  resource Structure, inclusive at the given second. Missing keys return
  Number zero, Boolean false and the empty Date.
- `Select([startDate], [endDate], [indexedProductFilter], ["Asc"|"Desc"])`
  returns the existing typed register selection. Selection orders by Period,
  then declared dimension order using the measured raw-reference key. Range
  boundaries are inclusive. Before the first record fields are Undefined;
  exhaustion retains the last record and further Next remains false.
- `SliceFirst(Date, [filter])` / `SliceLast(Date, [filter])` return a bounded
  ValueTable read view with seven columns. Filters are omitted/empty, complete
  Product+Variant, or indexed Product only. Resources, Note and typed Product
  references can be read; references use the same metadata snapshot as catalogs.

The first slice column is literally **`Период`**, not an English `Period` alias.
Other columns follow dimensions, resources and attributes in metadata order.
The selection field itself accepts Period/Период. Native slice row order is not
specified by the primary method contract and did not match a general physical
or composite-key ordering rule in the two captures. Do not rely on slice row
positions: use `FindRows(fullKey)`, then read values. No fabricated sorting rule
is used to make historical positional observations match.

## Explicit restrictions

Returned slice views support Count/Get/index/iteration/FindRows and column names.
The Period column uses the existing Date TypeDescription **provisionally pending
its final native probe**. Other column schemas, schema mutation, cell mutation,
copy/sort/index collections and serialization of this specialized view fail
clearly; internal untyped materialization is not exposed as a native schema.
Ordinary constructed ValueTables retain their existing behavior. These refusals
are implementation boundaries, not claims that native 1C forbids table mutation.

`!todo`: admit remaining native column descriptors and mutable result-table
operations only after relevant type/default/coercion evidence. Dynamic catalog
TypeDescription/codec guards are not relaxed here. Other periodicities,
recorder-bound mode, Boundary/PointInTime, subsecond normalization, arbitrary
filters/order, negative dimensions, totals/history, public register mutations,
free-slot chains and extensions remain unsupported.

## Evidence boundary

Minimized regression fixtures contain selected generated CONFIG, declarations,
raw records, historical programs and observations, not authentication/session/
installation data. The raw original authenticated report stays private.
Synthetic transport replay checks 90 of 96 observations per captured context;
only the six historical positional SliceLast key probes are explicitly excluded
from parity claims, while their original bytes remain retained. Final-source
native acquisition uses complete-key slice checks instead and remains required.
This checkpoint alone is **not actual frozen `.1CD` parity**.
