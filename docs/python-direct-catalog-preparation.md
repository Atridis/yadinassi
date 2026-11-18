# Generated catalog BeforeWrite

Current scope update: admitted standalone direct modules now have a separate
[owned transaction lifecycle](direct-standalone-transactions.md). This does not
admit externally supplied ambient transactions or widen source-handler grants.

The default direct backend now runs the selected catalog object module as
ordinary generated Python functions. `_prepare_catalog_object` still constructs
its small `_ObjectInterpreter` only to obtain the existing five pure host
functions, two constructor bindings, message sink and schema metadata. It never
calls that interpreter's execute, execute_program, block, call or visitor path.
Explicit legacy backends retain their existing execution path.

## Preserved product boundary

`BSLCatalogObject._write` is unchanged: it selects source using backend policy,
checks source/schema identity, owns the writer transaction, invokes validation
under the lock, refuses Boolean cancellation, rebuilds the final draft, and
retains uncertain-commit/retry handling. The generated validator has no Write
service. A denied write can change the disposable candidate but cannot durably
persist it. GetObject reads during a write use the writer's same read view and
check database, configuration generation, catalog schema and reference snapshot.

Source size, entry signature, routine collisions, AST/method/member restrictions,
field setters, tabular ownership, message limits and exact Boolean cancellation
remain. The static source validator's member inventory now includes schema
sections, row fields and line-number names, matching the already-existing runtime
member inventory; without that correction it rejected the original main-demo
module. Every branch is checked before source effects.

External names access the actual object through its typed setters/getters.
Explicit host dispatch is limited to adopted same-catalog-root objects,
references, sections/rows, owned messages and maps. There is no arbitrary Python
attribute access. Private source variables remain native generated locals.

`New Соответствие` in this narrow validation profile deliberately constructs the
existing BSLMap. Its value-key semantics for immutable catalog references are
required by duplicate-warehouse validation. The experimental raw `_TypedMap`
uses identity for such objects and would miss equal, separately materialized
references. This costs explicit method dispatch at map operations, not a return
to AST/VM execution. No performance claim is made for this patch.

## Deliberately not transferred

The old interpreter's per-AST-node step count, Decimal object-size/exponent
quota, and cumulative UTF-8 accounting of every intermediate result are execution
resource quotas, not catalog field/schema checks. They are not copied into the
generated route. There is no per-expression observer. Extremely expensive local
arithmetic, recursion or allocation is not given a new sandbox/resource guarantee;
Python exceptions before commit still unwind the existing writer transaction.
Existing field, section-buffer, message and persistence constraints remain.

## Verification

Eight focused real SQLite/main-demo tests pass: original trim and durable write
with legacy execute methods forbidden; three-message cancellation without a
record; duplicate separately materialized references refused without altering
the saved section; marked warehouse refusal; source replacement refusal;
unavailable methods rejected before candidate effects; explicit transactions
cannot bypass validation; and host-only preparation does not write. Full database,
query, posting and application UI parity are separate integration work.
