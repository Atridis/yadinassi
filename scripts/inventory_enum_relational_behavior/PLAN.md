# Direct enum relational reporting: independent native packet

This packet is being prepared. It contains no native observations or expected
outputs and makes no runtime parity claim.

The proposed host surface is exact inventory-enum-v1 (physical16), one direct
Query.Execute with ordinary enum IN/NOT IN arrays or one-column uncorrelated
SELECT, same-enum CASE/ISNULL, derived SELECT and UNION/ALL. Persistent packages,
TempTablesManager, INTO/DESTROY, external tables, reference Unload and enum
ordering remain outside the new grant. Existing profiles14/15/forms15 and their
storage/layout contracts do not change.

## Useful report

Join catalog products to optional stock, use ISNULL(Stock.Unit,Product.Unit),
filter selected units, and aggregate that derived result. Another direct report
can UNION ALL balances and unposted receipt lines before grouping by Product and
Unit. Results remain typed cursors; no writes or posting authority are implied.

## Twelve observation groups

1. Ordinary Array/FixedArray membership syntax: IN (&Values) versus IN &Values,
   with owned member/typed-empty and equality controls.
2. IN/NOT IN with empty, NULL-only, duplicate and valid+NULL arrays; nullable
   outer-join operand versus actual typed-empty enum.
3. Owned other-enum/mixed arrays and bounded wrong String/Number controls;
   observe refusal versus no-match, never infer assignment conversion.
4. Ordinary membership in WHERE, ON, HAVING and CASE conditions.
5. Same-enum CASE/ISNULL output: members, empty, NULL, omitted ELSE and types.
6. Mixed enum/scalar conditional result controls, including empty input and
   unselected branches. Wider native types do not oblige host admission.
7. Derived enum projection, equality/group/DISTINCT/COUNT(DISTINCT), nullable
   join and an empty typed inner source.
8. One-column uncorrelated membership SELECT/UNION, duplicates/empty/NULL and
   other-enum controls; correlated queries are not part of this packet.
9. UNION/ALL: same-enum identity, typed empty/NULL, duplicates, empty arms and
   mixed-enum output controls. Metadata matters even without rows.
10. Balance/Turnovers/BalanceAndTurnovers through derived/union, retaining
    explicit dimension dependencies and existing typed virtual filters.
11. Array mutation before and between Execute calls; a prior result is detached
    while a subsequent execution observes current input.
12. Staged posting, rollback and committed repost through composed queries.
    Host-only single-lease/issuer proof remains a separate regression obligation.

## Acceptance boundaries

The fixture reuses the established enum inventory schema, not a new storage
format. Every material field/enum target/order and executable module is redumped
and checked. Each group uses isolated case data. Execute refusal controls use a
finite token; setup/write/readback and row-serialization failures remain errors.
Exactly12 ordered bounded records, source/module/nonce witnesses, process exit
and quiet, and isolated cleanup are required before outputs may be exported.
Old native packets are regression evidence only, not this composition's evidence.

Host implementation must preserve exact canonical enum descriptors, complete
array-member ownership validation, current snapshot admission and all existing
parser/source/materialization/work budgets. Each execution shares one actual
owned read view across UNION/derived/subquery sources. Detached data is not a
lease or durable authority. Foreign/forged/stale namespaces, mixed-domain output
schemas and empty-source guards remain fail-closed; no UUID/custom-field value
alone can reconstruct an issuer capability.
