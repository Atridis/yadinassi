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

## Scoped resource accounting

Only catalog preparation opts into generated work/scalar checks. Ordinary direct
programs have no new per-expression cost. This profile does not call VM visitors
or `compiled_before`/`compiled_after`; generated code checks before each reached
expression/statement and at loop backedges, and validates each scalar expression
result before it can feed later operations or assignments.

A fresh preparation interpreter/context owns the remaining 16,384 work units and
1 MiB cumulative UTF-8 result budget. Routines and nested calls share those
counters; cached validators retain code/options only. Each string result is also
limited to 65,536 characters, checked before UTF-8 encoding. Exact Decimals must
remain finite, with the existing 256-byte object-size and adjusted-exponent ±64
bounds. Foreign types are neither coerced nor traversed by these guards.

These are local subset limits, not native 1C limits or identical VM node counts.
One operation can allocate its result before the result check: for bounded string
operands, concatenation can briefly produce up to twice the per-result bound.
Existing host formatting/source/field/container limits still apply; this is not a
universal host-allocation sandbox or rollback guarantee. Python recursion limits
may reject deep recursion earlier. Budget failure prevents successful preparation
and later persistence, but earlier disposable candidate changes are not undone.
The preparation AST profile does not admit Try/Except, so source cannot catch a
budget failure and continue consuming work. Closed/revoked authority stays fatal.

The cache key includes this profile and authority-checkpoint compiler options.
Tests cover intermediate expansion, cumulative multibyte text, numeric results,
loop/recursion work, cache reuse after success/error, hostile payload non-access
and unchanged ordinary compiler output. Existing native fixtures are not changed;
this restores a bounded local preparation contract, not native parity.

## Verification

Eight focused real SQLite/main-demo tests pass: original trim and durable write
with legacy execute methods forbidden; three-message cancellation without a
record; duplicate separately materialized references refused without altering
the saved section; marked warehouse refusal; source replacement refusal;
unavailable methods rejected before candidate effects; explicit transactions
cannot bypass validation; and host-only preparation does not write. Full database,
query, posting and application UI parity are separate integration work.


Policy-selected main_demo handlers may also run inside an owned explicit direct
transaction through the [guarded preparation lane](direct-transaction-beforewrite-design.md).
It uses the same writer snapshot, stages a frozen draft and never replays the
handler during uncertain-commit resolution. Unselected host preparation and
legacy explicit-transaction handler paths remain rejected.
