# Typed stock virtual dimension predicates: proposed acquisition and runtime boundary

Status: source preparation only. No new observations or runtime parity yet.
Base: checked private #292 + #295 union
`7e446f1693b38684fef45291652ce421a36978cd`, tree
`2fc3737f9f2049dc91e33c16d055cb3c755ecd51`.
The existing exact16 nonempty-condition refusal remains in production until
this separate composition has been measured. The two historical native12
packets are regression inputs, not evidence for typed virtual IN.

## Useful closed outcome

A BSL stock statement can select several products, warehouses or enum units
and scalar dimensions before totals reduction, without inventing SQL, copying
an unbounded movement table, or using assignment conversion. Balance,
Turnovers and BalanceAndTurnovers share one small predicate surface. None,
Day and Month retain the existing period contract and ordinary dates.

Proposed leaves are `Dimension = &Value` and `Dimension IN (&Values)`;
the latter's exact syntax is still a hypothesis. `IN &Values` is a separate
control, not an assumed equivalent. Only a bounded parameter Array/FixedArray
is proposed, not a literal expression list. AND and parentheses combine leaves.
Dimension names are unqualified, declared register dimensions only. No resource,
attribute, recorder, period-field, dereference or alias lookup in this argument.
No OR, NOT, inequality, IS NULL, arithmetic, subquery, hierarchy or auto-WHERE
pushdown. The caller can still use existing residual algebra within its current
grant; this work does not unlock ordinary EnumRef IN, conditional expressions,
ordering/MIN/MAX, packages, derived/temp/external/UNION paths or Unload.

Optional slots stay exactly where already measured:

- Balance(&At, condition)
- Turnovers(&Start, &End, [Day|Month|empty], condition)
- BalanceAndTurnovers(&Start, &End, [Day|Month|empty], empty, condition)

Explicit completion modes and missing required dates remain closed. Empty
condition slots remain legacy unconditioned behavior, not an always-true new
condition. Scalar14/core15/forms15 admit only their existing field kinds;
EnumRef dimensions require the exact existing format16 inventory source.
No physical format, schema encoding, source importer grant, DDL or migration
change is proposed. No UI/report transport changes are included.

## Binding, execution and budgets

- Reuse exact Array/FixedArray snapshot machinery to capture a detached tuple
  once per Execute (or existing admitted package execution). No arbitrary
  iterable, callback, nested array or duck-typed collection.
- New virtual IN has at most 256 supplied members before deduplication; at most
  16 leaves and nesting depth16. Existing text/token/comparison/parameter limits
  remain. Repeated values/parameter uses do not hide allocation charges.
- Freeze is not ownership proof. Validate every supplied reference, including
  every array member, even if an earlier AND term or empty list excludes all
  rows. The existing top-level enum-parameter loop does not cover list members.
- CatalogRef keeps exact manager/type/metadata/method-component identity and
  the current family/database/target rules. No existence reads, callback
  equality, fabricated same-UUID reference or wrong-catalog coercion.
- EnumRef uses the existing canonical binding.owned_key identity check, never
  assigned(). Foreign/fabricated/stale/root-generation-mismatched references
  are refused. An owned different-enum value never becomes target empty;
  whether it is a no-match in this new argument is an explicit native question.
- Scalar kinds are exact String/Decimal/Boolean/BSLDate. Apply existing query
  safety bounds, not storage-assignment truncation, rounding or empty coercion.
  Numeric signs/scales and dates are compared as values. String matching must
  be resolved by observations, not copied blindly from residual casefold or
  totals UCA grouping. No claim of arbitrary regional/native collation.
- NULL is not an empty reference, empty string or Undefined. Array NULL and
  empty-list result shape are measured separately. No new scalar-NULL
  SetParameter API is implicit. Unsupported mixed kinds remain explicit host
  refusals unless the measured narrow composition is deliberately admitted.
- Compile immutable per-field typed key sets only after full member checks.
  Validate/bind before the data-scan lease; existing enum lifetime/source
  admission can itself perform read preflight, so do not promise zero begin_read.
  Revalidate current owner/lifetime inside the one actual query view. Never
  discover a writer from backend._active or create authority from a cached key.
- Full physical scan, row decoding, all schema fields and input row/cell/text
  charges remain before selector exclusion. Even empty IN must scan/validate;
  malformed excluded rows, stale sources and over-budget input remain errors.
  Parameter/set materialization and membership work share existing package
  budgets; limits are not raised. Hash keys contain exact built-in primitives,
  never arbitrary user equality/hash/presentation hooks.
- Group dimensions come from every actual SELECT/WHERE/GROUP/HAVING/ORDER/ON
  dependency, not condition-only fields. Keep UUID->value mapping aligned with
  that subset. Legacy unconditioned grouping remains unchanged.
- Dimensionless nonperiodic Balance/B&T zero aggregate is a new composition
  gate, not inferred from old CatalogRef capture. _zero_balance_row must receive
  the exact owned enum_domain for16, like net sums and StatementReducer; no
  fallback to a scalar validator. Periodic empty/carry rows and Turnovers all-zero
  policy remain observation-bound. Generated output is charged before WHERE/TOP.

## Important routing seam

Generic syntax.Membership currently causes BSLQuery.execute to choose the
package executor, which deliberately rejects enum inventory. Do not remove
that guard merely to make virtual IN work. Prefer a dedicated virtual-membership
AST node traversed by walk_nodes but not classified as ordinary extended
membership. The direct relational path must snapshot virtual array parameters
once before planning, while existing package paths continue using their one
snapshot. Do not add a second source connection or relax ordinary membership.

## Independent native packet: 12 proposed groups

Each numbered group is a finite raw observation, not an expected golden value.
The observer records row count, exact scalar totals/types and source-owned logical
reference labels, without native GUID serialization or reference Unload. Dates
stay in ordinary2024, including month boundary and carry. Query refusals that
are deliberate syntax/type controls are caught and identified; unexpected setup,
material-redump or partial observer failure is not accepted as a completed case.

1. **Scalar equality / Balance.** String, Number, Boolean and Date dimension
   parameters independently; narrow string case/accent/trailing-space controls
   and a numeric parameter with extra fractional precision establish comparison
   rather than assignment semantics. No calendar-extreme sweep.
2. **Scalar array membership / Turnovers.** The same four kinds with exact
   arrays, duplicates and an AND intersection. Observe totals, not just success.
3. **CatalogRef + EnumRef equality / Balance.** Product and Unit separately,
   then Product + Warehouse + Unit AND; two units for the same product/warehouse
   make unwanted grouping or empty coercion visible. Include grouped output.
4. **Reference array syntax.** The identical Product/Unit sets using Array and
   FixedArray, with `IN (&Values)` and `IN &Values` as separate controls on
   default Turnovers. A rejected spelling does not invalidate the valid control.
5. **Mixed selector across all virtual tables.** Product/Unit IN combined with
   scalar equality and Warehouse equality, default Balance/Turnovers/B&T. Compare
   quantity and amount with a scalar-only projection, not assumed dimension rows.
6. **Day periods.** The same mixed condition on Day Turnovers and B&T, with carry
   before start and movements inside the period; capture exact bucket boundaries.
7. **Month periods.** The same mixed condition on Month Turnovers and B&T, spanning
   an ordinary month boundary and sparse carry; no new completion mode.
8. **Typed empty and missing keys.** Catalog empty, missing nonempty owned GetRef,
   enum typed empty, equality and singleton-array controls. Contrast scalar-only
   versus requested dimension output to observe zero-row/zero-aggregate shape.
9. **Empty arrays and NULL members.** Empty, NULL-only and valid+NULL arrays in
   the three table families. Observe selection and zero shape only; AND-only
   observations do not establish the general truth algebra of NOT/OR/NULL.
10. **Wrong type without adjustment.** Wrong scalar kind and canonical other-enum
    scalar/singleton-array/mixed-enum-array controls. Distinguish refusal/no-match
    from a target-empty match. Host foreign/forged/stale guards are separate tests,
    not native parity claims. Do not enlarge old wrong-catalog behavior by analogy.
11. **Projection/dependency composition.** Condition-only Unit versus projected
    Unit; nonprojected dependency in residual WHERE/GROUP/HAVING, scalar ORDER
    and JOIN ON. Include an unmatched LEFT JOIN's NULL. This is not enum ordering
    or general enum membership and does not admit packages/derived sources.
12. **Current transaction and frozen parameters.** Staged document posting/query,
    rollback, committed repost and repeat query; change the supplied array before
    a subsequent Execute and observe the new selection. No hidden reader, native
    session persistence or cross-VM transaction authority is inferred.

Fixture plan: retain the existing owned Products/Warehouses, Receipt/Issue,
Stock and Units/States vocabulary in a NEW packet. Add only four admitted scalar
dimensions to that packet (Batch String, Grade Number, Reserved Boolean,
LotDate DateTime) and matching document-line/handler fields. This stays below
existing dimension/field bounds. Both native installed XML and authored runtime
source must have material projections including every new dimension, qualifier,
reference target and handler. Existing packets/fixtures/hashes remain unchanged.
No enum form grant, new enum storage type or actual-user database is involved.

## Planned affected files and release gates

Runtime after observations: query_parser.py (isolated virtual AST/grammar),
accumulation_query_conditions.py (closed typed key binder), accumulation_queries.py
(selector budget/domain propagation and explicit16 gate), queries.py and narrowly
relational_queries.py (single-execution parameter capture/data-plan handoff).
No planned edits to enum codecs/namespace/issuer lifecycle or storage admission.
A discovered required change there needs its own review before expansion.

New packet: scripts/inventory_typed_filter_behavior/{PLAN,fixture,route,observe,
owned XML/BSL,runtime_source}; native bootstrap/profile/probe and a separately
branch-gated workflow later. New offline, typed binder/runtime, unchanged-capture
replay and source inventory tests; profile docs and a BSL stock example. README
stays unchanged. Native group count12 is a proposal until root notice; offline
and host collection counts must be reported before execution. No acquisition,
CI, publication or tests are authorized by this plan file itself.

Host regressions include exact type/issuer/cross-DB/family/generation guards,
all-array-members validation, no callbacks,256/257 member and16/17 leaf bounds,
shared cells/text/work charges including duplicates, excluded-row corruption,
raw SQLite edits at unchanged generation, staged/rollback ownership, same actual
snapshot, grouping dependency and zero-domain paths, close/cleanup failures,
legacy14/15 behavior, old enum residual/package refusals, and old immutable native
captures. A positive result on the old12 packets does not fulfill new12 replay.
