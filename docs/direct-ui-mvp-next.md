# Direct catalog/document UI and query iteration

This draft extends actual `main_demo` workflows rather than restoring legacy
statement dispatch. Public form items/commands/tables use current-owner public
protocols; original catalog source edit/list events execute generated functions.
Document RPC invokes prepared handlers with the existing endpoint, side, arity,
revision and delta checks. Accepted failing RPC retains its original partial
state/revision semantics; this is not a transaction rollback promise.

Host-bound SQLite forms are admitted only by the form boundary. Configuration
modules still reject database contexts. A form retains its exact selected
context; replacing it during execution is rejected. No general database
namespace is granted by this admission.

Native Date arithmetic delegates to the existing pure date algorithms. Native
list query parameters use the existing Execute-time frozen parameter snapshot:
changes before Execute are visible; changes during scanning are not.

## Prepared namespace correction (audit 5)

Verified bug: preparing `Catalogs=1;` without a database and reusing the plan in
a database VM allowed a write which ordinary database compilation rejects.
The existing prepared contract now includes the DB/non-DB namespace profile,
matching the compiler's external-name and constructor options. Cross-profile
reuse rejects before effects; same-profile reuse binds fresh current VM state.
This is not a database-identity cache or another AST pass.

## Known limits

The previous per-AST execution observer is not restored. The old source-event
test that manually zeros `_EventInterpreter._remaining` still differs. Source
hash/schema admission and the existing atomic writer remain in place. This is
not full parity or a claim that every MVP scenario now works. Date Map key
identity/equality remains a previously observed separate gap. Python 3.10
code-position support remains a known direct-backend incompatibility.

Audit 5's BeforeWrite plan reuse and DB-independent scalar specialization are
not implemented in this iteration. `check_owner` imports are hoisted without
freezing live policy attributes. An isolated 15-pair configured-form loop test
reported median 22.45 -> 16.92 ms, identical output and 10,001 checkpoints; these
are local loop measurements, not an end-to-end application speedup claim.

Combined verification: 97 tests, 93 passed and four errors in the expanded query
membership suite: two unsupported `ValueTable` constructors and two missing
`InformationRegisters` namespace cases. The included main-demo host, document
UI, query examples, RPC, prepared-profile and provenance suites passed. These
four unsupported scenarios are recorded, not converted into skips or fallback.
