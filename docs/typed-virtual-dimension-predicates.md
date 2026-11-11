# Typed stock virtual-table predicates

This is an explicit query extension for `inventory-enum-v1` (physical format 16),
not a new storage format or migration. Existing scalar 14, reference 15, and
forms-15 profiles retain their previous CatalogRef equality-only conditions.

A stock query can select movements using declared String, Number, Boolean, Date,
CatalogRef and EnumRef dimensions before the existing bounded reduction:

```bsl
Units = New Array;
Units.Add(Enums.Units.Piece);
Units.Add(Enums.Units.Pack);
Q = New Query("SELECT QuantityOpeningBalance, QuantityClosingBalance
    |FROM AccumulationRegister.Stock.BalanceAndTurnovers(
    |&StartAt, &EndAt, Month,,
    |Product=&Product AND Warehouse=&Warehouse AND Unit IN (&Units))");
Q.SetParameter("StartAt", Date(2024,2,1));
Q.SetParameter("EndAt", Date(2024,3,31,23,59,59));
Q.SetParameter("Product", Catalogs.Products.FindByCode("P"));
Q.SetParameter("Warehouse", Catalogs.Warehouses.FindByCode("W"));
Q.SetParameter("Units", Units);
Result = Q.Execute();
```

The same condition slots are `Balance(&At, condition)` and
`Turnovers(&StartAt,&EndAt,periodicity,condition)`. Empty periodicity means no
period grouping; the closed Day/Month calendar contract is unchanged. Date
bounds still use the explicit practical host range, not a claimed platform limit.

## Closed grammar and ownership

Only unqualified `Dimension=&Parameter`, `Dimension IN (&ArrayParameter)`,
parentheses and AND are admitted. IN requires its parentheses and one exact
Array/FixedArray parameter. OR, NOT, inequality, literals, subqueries and arbitrary
iterables are not added. Ordinary relational enum IN, enum packages, derived
sources, ordering and Unload keep their existing refusals.

Each direct Execute freezes array contents once, then binds every used member
before opening its data-scan lease. Changing the Array after SetParameter affects
the next Execute; changing it after binding cannot change the current execution.
Foreign-family, stale or fabricated enum references are refused through the
canonical issuer. Catalog references retain exact metadata/callback and target
catalog guards. No existence lookup, coercion to typed empty, or assignment
normalization is performed.

Limits are 256 members before deduplication, 16 terms, depth 16, and the existing
query token/comparison/cell/text budgets. Repeated terms and reused arrays charge
binding cells/text again before key construction. Keys are immutable primitives,
not user callbacks or reference equality/hash methods.

## Measured semantics and limits

Native 1C 8.3.27.1508 run 43105381775 produced twelve complete groups against
source tree `e18012018b88db01deb282dcde58f1c9f591af75`. The immutable capture retains
material XML/module witnesses, source hashes, process exit/quiet and cleanup.
It is native evidence, not by itself a host replay verdict.

The packet observes all three virtual tables, Day/Month, scalar/reference arrays,
projection dependencies, joins, staged posting/rollback, committed reposting and
array changes between Execute calls. Empty or NULL-only lists match no movements;
NULL is not an empty reference. Dimensionless non-periodic Balance/B&T return a
zero aggregate while Turnovers has no occurrence. Projected dimensions retain
sparse empty results.

Owned other-enum values do not match, including mixed valid/other-enum arrays.
The measured wrong scalar is specifically Number compared with String `"1.25"`:
no match, not assignment conversion. Other cross-kind combinations remain refused.
Longer-than-field String and extra-scale Decimal parameters are bounded query
values, not truncated/rounded storage assignments.

Only the selector uses pinned caseless UCA with canonical normalization and
trailing ASCII-space removal. This matches the measured `lot`/`LOT`/`lot ` and
composed/decomposed café controls. It is not arbitrary locale parity, Unicode
whitespace stripping, or a change to residual WHERE or legacy grouping.

Every physical source row and all its fields are still validated and charged
before exclusion, including unprojected enum fields. Conditions affect reduction,
not integrity admission. Condition-only dimensions do not force grouping; actual
SELECT/WHERE/ON/GROUP/HAVING/ORDER dependencies do. Result budgets are enforced
before residual WHERE/TOP, and one owned actual query snapshot is retained.
