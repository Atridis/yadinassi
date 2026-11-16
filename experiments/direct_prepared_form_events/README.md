# Prepared catalog source events and object helpers

Base: `2f29a70c`. Runtime changes are confined to form_event_simulation and
python_direct_form_events; no posting, SQL writer, renderer or generic VM path.

An event plan contains generated code plus an exact admitted source/profile key.
The product/list owner is the existing catalog manager; verified scalar forms
use their existing backend, because CatalogEditor creates a fresh draft session
for every action. Standalone FormDraftSession uses its own slot. Each owner holds
only its last event plan, not an unbounded cache. Keys include source, transform
mode, full catalog schema or scalar source/XML binding, constructor names, module
layout, native target, backend and repairs. Controls/receiver/message sinks are
never captured in these plans. Compilation transforms only an owned AST copy.

The real object module's exported preparation/check routines reuse the existing
prepared_validator code plan. That same module already supplies BeforeWrite.
Every call still creates a fresh _ObjectInterpreter, boundary and cancellation
cell, with the current receiver and write view. Source selection, current source
and XML/schema admission, private parse and verified before/after storage reads
remain in their callers. A cache hit is not permission, source ownership or
transaction admission. No source effects happen while preparing a plan.

Regression evidence: real editor repeated Description/Save compiles once across
fresh scalar draft sessions; event and object code reuse produces fresh refusal
messages/cancellation; changed source or closed backend cannot use warm code;
changed schema/options invalidate; failure after a private setter neither adopts
nor retries; existing product/list, SQL refusal and no-VM UI tests remain intact.

## Actual UI measurement

`paired.py BASE_REPO CANDIDATE_REPO --python PYTHON` runs seven alternating
fresh-process pairs through MainDemoHost's real original catalog forms. Each has
six Description+Save cycles for kind and product. Product has one actual stored
warehouse and kind reference. Every saved name/state and final saved warehouse
count are checked. No Chromium or native 1C parity claim. Runtime setup and first
cycle are excluded from warm medians; first-cycle samples remain in results.

Warm medians in milliseconds, baseline -> candidate:

| Original UI action | Baseline | Candidate |
| --- | ---: | ---: |
| Kind Description | 45.62 | 31.90 |
| Kind Save | 77.67 | 61.85 |
| Product Description | 58.56 | 22.99 |
| Product Save | 161.09 | 72.00 |

All samples and exact runtime hashes are in results.json. These measurements do
not include the separate canonical-validation-only optimization. Parsing and
source checks still cost time; they were deliberately not folded into this code
reuse slice.
