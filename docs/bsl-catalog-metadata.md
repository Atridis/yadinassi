# Experimental offline BSL catalog metadata

Local implementation candidate; fresh native **public BSL adapter** acceptance
is still required. PR165 measured the source-bound native surface and CONFIG
projection, not this new interpreter implementation.

`Metadata` / `Метаданные` and `.Catalogs` / `.Справочники` are lazy. Merely
looking them up, parsing code, or taking an unrelated branch does not open a
file or require a database. Executed `Count()`, `Find(name)`, catalog property
or index lookup loads a bounded CONFIG-only snapshot through
`FileDBContext.catalog_metadata()`. Missing database context produces the normal
catchable `db required for further code execution` error. No catalog record,
PARAMS/DBNames binding, catalog manager or write is required or exposed.

Supported members (case-insensitive aliases):

* collection `Count()` / `Количество()`, `Find(name)` / `Найти(name)`;
* catalog access by name property or string index;
* integer numeric index only for a single-catalog projection (index zero);
* catalog `Name` / `Имя`, `FullName()` / `ПолноеИмя()`;
* stable object identity within one interpreter's loaded snapshot; read-only
  properties and index entries.

`Find` uses case-insensitive name lookup; absent names return `Undefined`.
String and Number arguments use the existing BSL scalar String conversion, so
numeric misses follow the general lookup rule, not a special `Find(1)` branch.
Other argument families are explicitly outside this profile. Method/property
collision precedence is unmeasured: catalog names matching collection method
names require `Find` or a string index; bare property access is rejected. Multi-catalog
names and count work, but numeric ordering is rejected rather than inventing
an order absent native evidence. English `FullName()` returns the measured
Russian `Справочник.` prefix. Snapshot values are derived from CONFIG, not
fixture names, UUIDs, values or predicted catalog counts. Successful snapshots
are cached for that interpreter; errors are not cached. Use a new interpreter
for another offline postimage.

The source must be a caller-owned, consistent **offline** copy. Read-only open,
finite parser budgets, regular-file checks and descriptor identity checks before
and after traversal do not establish transactional consistency of a live base.
Existing CONFIG profile restrictions remain: this is not a universal metadata
resolver, and unsupported/ambiguous layouts fail closed. The native evidence
covers the owned fixture at updated, loaded-but-not-applied and applied states;
it does not prove universal applied-state selection for arbitrary databases.

Not implemented: `Attributes` / `Реквизиты`, configuration properties, iteration,
metadata types/reflection, catalog managers, rows, writes, queries, or CF/DT
lifecycle commands. Native probe cases07/08 (Payload length32/32/64) remain
**storage applied-discriminator controls**, explicitly outside this BSL surface;
they must not be counted as interpreter parity or silently hidden. The other24
probe cases are the exact supported replay target, including errors, aliases,
identity and the post-write unchanged-name observation.

## Acceptance gate for this candidate

The exact unchanged probe is SHA-bound in
`scripts/native_1c_db_oracle/metadata_catalog_runtime_readback.py`. Unit replay
uses a named **stub** metadata source and matches144 supported observations over
six captures; actual-file synthetic tests separately exercise CONFIG-only files
through the public context/interpreter. Neither is fresh native acceptance.

A new owned native run must stage and authenticate the interpreter dependency
closure (including `pyuca` and its UCA data), add it and the helper to the exact
source inventory/report validation, and call public `readback()` inside the
existing `inspect_frozen_catalog` hash/quiescence envelope on each same frozen
postimage. The current36-file measurement bundle does not contain this closure.
Require24 supported matches for both contexts at each of the three lifecycle
states while retaining original Payload32/32/64 CONFIG/native controls. Record
new source/tree and artifact digests and obtain an independent review. Existing
PR165 acceptance must not be relabeled as acceptance of this runtime candidate.

The separate [opt-in runtime native lane](metadata-catalog-runtime-native-lane.md)
prepares that full bundle and comparison locally; its implementation is not
a native acceptance result.
