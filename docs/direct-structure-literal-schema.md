# Literal Structure schema lowering

`New Structure("category,quantity,price", ...)` now prepares field names once
while translating. Private immutable schema records normalized keys, final
spelling and the source value argument index. Repeated normalized fields retain
the first insertion position and last spelling/value. Runtime construction only
creates the native `_DirectStructure` backing dict and sets its composition
version to the number of distinct keys. No per-instance split, identifier check,
casefold or `structure_insert` dispatch is performed.

Every supplied value argument still evaluates left-to-right, including ignored
extra values. Missing values remain Undefined. Invalid literal schemas use the
unchanged runtime constructor, so argument effects/errors precede the schema
error exactly as before. Dynamic property-name strings also retain that route.
No new VM wrapper, generic dispatcher, authority gate or SourceMap change.

Six focused tests compare actual Interpreter and direct behavior for duplicate
fields/Unicode casefold, whitespace, missing values, extra argument effects,
invalid schema/error precedence, dynamic names, fresh objects and payload aliases.
The composition-version test also compares the existing dynamic constructor.
33 targeted tests (new schema + existing Structure/Array-method + naked collection
tests) pass normally and under `-O`; no full-suite/native1C parity claim.

## Synthetic measurements

Seven alternating fresh-process pairs against354f3e56, five warm runs per sample.
The same invoice1000 and graph1000 fixtures retain numeric, alias and complete
Observe-event controls. Both variants use the same semantic15 experimental
profile with live module state; no quota/authority flags. Preparation is excluded
from warm timing; cold includes creation/parse/prepare/first execution but excludes
Python startup/imports. GC remains enabled. Only this schema slice differs.

| Case | Before warm median ms | After warm median ms | Median paired ratio | Paired range |
|---|---:|---:|---:|---:|
| Invoice1000 |8.952|5.713|1.520|1.355–2.456|
| Graph1000 |9.826|8.719|1.156|0.935–1.450|

Invoice improvement is consistent in these pairs; graph has noise crossing1,
so no consistent graph speedup is established. Cold medians52.87→46.59ms and
70.83→67.14ms are not a claim of stable preparation improvement. This is a
synthetic workload comparison, not product throughput or fresh real1C evidence.
Raw paired data/source hashes are retained with the local research results.
