# Reuse prepared BeforeWrite code, not write authority

A catalog manager retains one last `PreparedCatalogValidator`: owned admitted
AST and generated declaration factory. The key includes exact source text,
complete frozen CatalogSchema, current native target, backend, repairs and the
fixed constructor profile. External names are derived exclusively from that
schema and the fixed object aliases. The constructor set matches the closed
_ObjectInterpreter allowlist. No receiver, message sink, Reference, write view,
execution result or invocation closure is cached.

On a miss, the conservative source validator returns its parsed AST, eliminating
the previous second parse, then the direct compiler lowers it once. The public
`validate_catalog_object_source` API retains its validation-only return value.

The writer selects current source as before and resolves any pending receipt
first. A known committed receipt returns before preparation or BSL execution.
Only after confirmed absence (or a new write) does it prepare code, before
`begin_write`. The transaction still validates database, generation, full schema
and source manifest under the existing writer lock. Invocation checks the
prepared key again and creates fresh _ObjectInterpreter, Boundary, messages and
Cancel cell using the current candidate and transaction read view. Retry uses
the retained source and frozen submitted image, not new edited state.

This is not an authorization cache. Changes to source/schema/options invalidate
the single slot; private plan fields are implementation-owned and not a mutable
public AST API. No VM dispatch, per-node observer or new runtime-wide cache was
introduced. Creating the lightweight metadata interpreter is not optimized in
this slice.

## Measurement

`experiments/direct_prepared_validator/measure.py`, run with `PYTHONPATH=.:tests`,
uses a real temporary SQLite main-demo database and the original product source.
Five alternating baseline/candidate fresh-process pairs compare baseline
`a50c2de9` (local exact-tree equivalent of public `4858b78e`) with this change. Setup is excluded; first write is measured separately,
then ten real updates are timed. Each process reopens the stored object and
checks the final name, one warehouse row and no active transaction. Raw rows are
in `experiments/direct_prepared_validator/paired.json`.

- Ten warm updates, median: **821.15 → 164.50 ms**, about **4.99× faster**.
- First write, median: **77.52 → 69.69 ms**; noisy, no cold-speed claim.

These are actual write timings, not helper-only measurements or a universal
performance promise. Database, source and writer checks remain included.

The final run used CPython 3.12.14 (Clang 22.1.3) on a shared Linux host without
CPU isolation. `environment.json` records SHA256 of the three final changed
runtime files. This supersedes an exploratory run before the fixed constructor
profile was added to the key; published raw rows are from the final runtime.
