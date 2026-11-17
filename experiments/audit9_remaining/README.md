# Remaining audit9 candidates

Baseline: 9516625c113621be72343fa363a9558f32a30dea. Python 3.12.14.
Only SQL identifier quoting is changed in production; Map and module-local
prototypes below are measurement-only and deliberately not production APIs.

## Selected: bounded pure identifier quoting cache

quote_identifier checks exact str before hashing/equality. A 512-entry private
lru_cache stores only validated quoted strings, keyed by name and the current
byte limit. Empty/control/surrogate/oversized names still reject; exceptions are
not cached. This does not cache schema validation, source admission, transactions,
SQL results, receivers or permissions. Current integrity checks remain unchanged.

Seven alternating pairs use the original MainDemoHost/SQLite Description/Save
worker, checking saved values and the warehouse row. The benchmark replaces the
public function's code object with the **exact baseline** code so all imported
aliases use the chosen version. It restores code in finally. Cache is cleared
before every before/after cell. No tests/review processes overlap timings.

| Median ms, final series | Before | After |
|---|---:|---:|
| Kind Description | 9.156 | 7.156 |
| Kind Save | 31.835 | 22.878 |
| Product Description | 8.989 | 7.274 |
| Product Save | 42.803 | 30.616 |

Product Save improves in all seven final pair medians. Kind Save improves in
five of seven. Timing has substantial spikes, all retained. The first exact
series (quote_exact_first.json) showed Kind Save27.205→26.611 and Product
Save36.908→33.194ms; final results are quote_results.json. Thus no fixed universal
percentage is claimed. An earlier same-wrapper cache-on/off exploratory result
was replaced by exact-code comparisons and is not the evidence above.

62 tests normal and 62 optimized pass (quote cache, actual storage shape and
SQLite catalog sections). Independent review:50 optimized source/transaction/
storage tests pass. Cases include host hashing/equality traps before cache lookup,
Unicode/control/size rejection, changed byte limit, bounded eviction and proper
quote escaping. No fixtures or integrity gates were weakened.

## Rejected: inline specialized Map tokens

Seven alternating pairs of numeric/string event-count aggregation,20,000 events,
prepared execution. Prototype inlines token construction in specialized _TypedMap
get/set. Numeric median33.974→34.492ms (slower, four of seven pair medians slower);
string42.389→40.733ms (small gain, mixed pairs). Not a stable general improvement
worth duplicated token logic. Canonical BSLMap reference-key semantics untouched.
Raw source, all samples and result controls are in compute_results.json.

## Rejected: module Python locals

An intentionally incomplete generated-code prototype replaces module dictionary
reads with local variables and writes through to the live dictionary. It does
not provide synchronization after callbacks. Array aggregation6.833→5.519ms and
numeric sum24.779→22.045ms demonstrate the possible computation-only gain, but a
registered callback changing the For counter changes the result from correct10
to3. The experiment contains and records this counterexample. It is not a valid
backend implementation and is not connected to production. No general
flush/snapshot layer or new callback restrictions were added to chase this gain.

## Reproduce

```sh
python experiments/audit9_remaining/measure_compute.py
python experiments/audit9_remaining/measure_quote.py
PYTHONPATH=tests:scripts:. python -O -m unittest test_quote_identifier_cache test_main_demo_storage_shape test_sqlite_catalog_sections
```

The server/NoContext six-scenario blockers are unaffected by these performance
experiments. No full CI/native parity claim.
