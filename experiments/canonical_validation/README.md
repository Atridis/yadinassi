# Validation without allocating a discarded canonical copy

Baseline: public `33fa4961` (local exact-tree `7c38cb68`), including prepared UI
source-event code. Only two runtime files change: configuration_main_demo.py
separates full validation from detached-copy creation; sqlite_main_demo_profile
uses validation-only where it previously discarded canonical()'s return value.
Every current source byte hash and full schema comparison remains. Public
canonical() still returns a deep detached copy; validate_canonical() returns None.
The private parse witness is never exposed through either public API. This is
not an authority cache or an exemption for previously validated configuration.

Tests preserve cold/warm source drift, forged schema rejection, foreign equality
hooks and returned-copy poisoning coverage. New tests prohibit deepcopy during
validation-only storage checks, assert no return value and retain rejection of
invalid source/schema and mutated public copies. Independent review found no
blockers. The initial 36-test normal suite included parse-witness, storage
admission/shape and actual main-demo host actions.

## Actual UI measurements

Run in either checkout, with runtime dependencies installed:

```sh
PYTHONPATH=.:tests python /path/to/candidate/experiments/canonical_validation/measure.py
```

The identical script drives MainDemoHost against a real temporary SQLite
main-demo database. Setup, reference seeding, opening and the first save are
outside timing. Each process measures four Description changes and Save actions
for both Kind and Product, then reopens the saved object and checks the final
Description and absence of an active transaction. Five alternating fresh-process
baseline/candidate pairs are retained in results.json, including all samples.

Median of per-process medians, milliseconds:

| Action | Baseline | Validation only |
|---|---:|---:|
| Kind Description | 29.95 | 25.03 |
| Kind Save | 60.21 | 46.27 |
| Product Description | 24.43 | 19.52 |
| Product Save | 75.70 | 57.65 |

Shared Linux host, no CPU isolation. This is host UI protocol evidence, not
Chromium/native-1C parity. Hashes in environment.json identify the measured
runtime. Posting plan reuse is not included in this comparison. Parsing and
repeated source snapshots are not changed by this small validation/copy split.
