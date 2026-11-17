# Validate current catalog layout without constructing a discarded new layout

Baseline: `0cdb512cacbcec8c2d0502a64e0593c184b6e0b4`.

`validate_main_demo_ddl` previously ran creation preflight: a second canonical
check, codec/bounds/reference validation, fresh layout construction and SQL
construction. It then discarded the generated layout and SQL, loaded the actual
persisted layout, and constructed the expected SQL again for comparison.

The change extracts `_validate_catalogs` with the same codec, size, cardinality,
identity, name, hierarchy, enum-cell and reference-target checks. Existing-database
validation runs canonical and domain checks once, validates the catalogs, then
loads the **current** persisted layout and constructs its expected DDL once.
Actual sqlite_master, mappings, index vocabulary and resource checks remain.
Nothing is cached. Source, transaction and data-row validation are unchanged.
Creation still uses full `_catalog_shape` preflight, including generated layouts
and every SQL declaration before allocating a database file.

This is the fixed canonical main-demo profile, not admission for arbitrary new
catalog definitions. Canonical source/schema validation remains mandatory; the
removed generated-name checks cannot admit a forged alternate configuration.
Current persisted physical names are still checked by the load-layout routines.

## Reproduce

```sh
PYTHONPATH=tests:scripts:. python -B experiments/current_catalog_shape/measure.py
PYTHONPATH=tests:scripts:. python -B -m unittest test_sqlite_shape_validation
```

Seven alternating before/after pairs, each using fresh real MainDemoHost/SQLite
fixtures and the original scalar editor worker. The harness reconstructs the
baseline validator and `_catalog_shape` from the pinned commit and switches both.
Setup is excluded from timing. Saved trimmed values and product warehouse count
are checked. Warm medians exclude the first iteration in each fixture; every
sample is retained in `results.json`, including cold/first iterations.
Python 3.12.14 on Linux. All regression/reviewer processes had finished before
measurement began.

| Operation | Before ms | After ms |
|---|---:|---:|
| Kind Description | 9.615 | 8.829 |
| Kind Save | 31.255 | 27.493 |
| Product Description | 10.194 | 8.802 |
| Product Save | 42.692 | 36.484 |

All four operations improve in six of seven pair medians. Pair 2 regresses;
pair 3 is slower for both variants, consistent with environmental timing noise.
No samples were dropped for being slow. Aggregate Save reductions are about
12% and 15% respectively; these are specific host operations, not general engine
or native/Chromium speed claims. Do not add these gains to earlier slices.

## Validation

98 tests passed normal and `-O`: new shape tests, existing creation shape and
admission tests, transaction-local source, prepared source, read-handle lifecycle,
direct database and direct posting. New tests verify no creation-layout work on
the read path, exactly one expected DDL construction per catalog/section, one
canonical check, required current codec roundtrip, forged config/domain rejection,
and rejection of externally changed persisted layout. Existing tests cover
source corruption, rehashed changes, DDL/register corruption and concurrency.
Independent review passed 47 tests under `-O`, without blockers.

The whole profile is still revalidated; no authority cache, fallback, additional
runtime bookkeeping or performance thresholds were introduced. Full CI and native
parity are not claimed by this measurement.
