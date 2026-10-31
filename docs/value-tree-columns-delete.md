# Bounded ValueTree.Columns.Delete compatibility

For the explicit `linux-8.3.27.1508` target, `Delete` / `Удалить` now reproduces
DL14 and DS6 observations. Non-last deletion preserves rows and other cells.
The retained removed column has the same identity, empty Name and Title, and
Width 0. Its ValueType and writes remain unsupported after deletion.

Deleting the last column by Number or owned column empties the active rows and
schema. Old row references keep identity, but their cells, Owner, Parent, Level
and Rows become inaccessible. Previously saved child-row collections retain
Parent and forward Count and Add to the active root. This is a separate cause
from Columns.Clear: Get, Insert, Clear, iteration and other unmeasured operations
are not enabled on Delete-detached collections. Ordinary row removal never
obtains this forwarding. Schema can be rebuilt before a saved collection adds a
new root row.

DS6 separately verifies non-last named statements in both languages and rejects
named Delete expressions. The implementation preserves the existing shared
procedure-before-argument-evaluation policy; native evaluation order was not
measured by these literal-selector probes. Delete is procedure-only
on the Linux target. Named-last lifetime was not measured: nonempty trees keep
the existing guard and schema-only named deletion keeps legacy metadata behavior.
Non-Linux targets preserve their prior behavior, including expression policy.
No new native Windows compatibility is claimed.

## Evidence and limits

Original DL14: run [41135287284](https://github.com/Atridis/yadinassi/actions/runs/41135287284),
head `ef3de20d75ad33260e542f96be78481b3beb1d03`, 14 cases, 2,492 capture bytes.
Original DS6: run [41140659293](https://github.com/Atridis/yadinassi/actions/runs/41140659293),
head `bf1ce25ac3d5bbc8fcc72c1ba93488e00fe733c6`, six cases, 1,399 bytes.
Both acquisitions passed native controls, client/server agreement and cleanup;
both original interpreter comparisons mismatched. Their attribution stays
unchanged in `tests/fixtures/value_tree_columns_delete/provenance.json`.
The DS6 run's separate ordinary collections timeout is not reclassified.

Exact server and generated-client replays and the real production comparison
runner test the new implementation against both immutable captures. The required
automatic DL14 lane is restored; DS6 remains reproducible but offline. Fresh
final-head native and platform checks are separate merge gates.

Host graph/owner, work, text, numeric and default-value checks are local resource
policies. They reject corruption before mutation without inspecting opaque cell
values. They are not assertions of additional native limits or coercions.
