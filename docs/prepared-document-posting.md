# Reuse source-bound posting code

PostingRuntime already owns a canonically admitted configuration and the AST
produced by compile_handlers. It now retains the exact bound source bytes and
one last generated plan per document type. The key includes source path/digest/
bytes, full DocumentSchema, native target, repairs and fixed Query constructor
profile. Code/signature metadata only is retained, not receivers, services,
transactions, Cancel slots or event closures. Private runtime AST/configuration
fields are not a mutable-source API.

A miss compiles before the document writer's own execution/savepoint. An outer
caller-owned transaction can already exist, as before. Plain Write with no
selected BeforeWrite/OnWrite handler does not compile an unused Posting body.
Each actual invocation still creates fresh interpreter metadata, boundary,
exports and reference slots, under admission(False), server/module scope and the
current native target. Family lifetime checks remain live.

Current writer source/schema checks, transaction staging, movement ownership,
Boolean cancellation, rollback and receipt resolution are unchanged. No AST VM
dispatch or artificial per-node execution quota is added. Replacing this code
cache does not grant permission to write.

Focused tests use original main-demo Receipt source for successful posting,
current Cancel/exception inputs, current transactional query results and rollback.
InventoryRootOperations tests execute that same original source and prove both
committed operation-ID replay and uncertain-real-COMMIT resolution call neither
prepared_posting nor PostingRuntime.write. Schema/target/compiler changes replace
the bounded slot; different admitted sources do not share a plan. Plain Write
without selected handlers avoids preparation.

Two older scalar PostingHostTests remain baseline failures: their Number(...)
call conflicts with the direct external Number field. That compatibility gap was
not changed or used as a false receipt-success test.

## Measurement

See experiments/prepared_posting. Five alternating fresh-process pairs against
local base 2f29a70c; CPython 3.12.14 on shared Linux, no CPU isolation. Setup is
excluded, first posting is separate, and warm totals include ten actual SQLite
reposts and all existing writer/source/transaction checks. Final changed runtime
SHA256 and complete raw controls are retained. This is not a universal posting
performance claim.

Final medians: ten warm reposts **340.23 → 162.47 ms**, approximately **2.09×**
faster for this original one-line Receipt case. First posting **34.52 → 33.15 ms**
is noisy and not claimed as a cold-start improvement. All ten processes agreed
on document/posted-state/movement counts (1/1/1), Quantity=5 and released SQL state.
