# Scalar editor source boundary composition

The UI already verifies its pinned coherent form/object source immediately before
execution and again before accepting a detached handler result. It now constructs
only the detached FormDraftSession inside these checks, instead of layering a
second independently verified consumer (constructor read, additional surrounding
reads, and two per-event reads). Description goes from six reads to two.

The private helper still validates exact backend/catalog/scalar types, the entire
stored binding and source bytes. It grants no write capability. Public
VerifiedFormDraftSession keeps its independent source reads and before/after
checks unchanged. No cross-operation source authorization cache exists. UI sticky
stale checks, source/backend identity, detached adoption and writer transaction
validation remain. Existing source drift between preparation and writer tests
remain unchanged; new tests inject drift after handler/preparation and prove no
adoption/write. Opening still validates the initial scalar image.

Reproduce: `PYTHONPATH=tests:. python experiments/scalar_editor_source_boundary/paired.py BASE CANDIDATE --python /path/to/python`.
Baseline local4b6a9394 has the exact public e1b2b9d4 tree. Seven alternating
fresh-process pairs run actual MainDemoHost/SQLite actions, assert normalized
saved values and warehouse content; first operation per profile is discarded.
Warm medians (ms):

| Profile | Operation | Base | Candidate |
|---|---|---:|---:|
| Kind | Description | 17.682 | 6.389 |
| Kind | Save | 37.998 | 26.089 |
| Product control | Description | 6.713 | 6.546 |
| Product control | Save | 33.958 | 34.076 |

These are host protocol timings, not Chromium/native 1C parity. No timing gates
or promises of generic speedup. Raw samples and exact source hashes accompany
this document. Product implementation is untouched by this slice.
