# Lightweight Table sorting and historic order

Blocking `test_native_target_sort` checks all 96 Python orders, record/cell/owner
and metadata preservation, numeric ordering and callback rejection. The readonly
`cells` snapshot contract is checked separately, not excused as collation.

`python -m tests.compatibility_native_table_sort` validates the unchanged fixture
and all 96 actual cases, then reports exact historic ordering differences. The
dedicated **Совместимость с 1С: известные расхождения** job in **Test and build**
publishes the report in the run Summary and as a `compatibility-differences-*`
artifact. The job is informational and is not a dependency of the required
verdict or release. Missing coverage, fixture/data corruption and execution
errors fail the diagnostic step and are labeled incomplete in the Summary,
not mistaken for zero differences. The job currently lists this exact-order
difference at low priority; it does not suppress other failing tests.

For the strict oracle use
`python -m unittest tests.compatibility_native_table_sort -v`.
It remains red on historical mismatches. Runtime and fixtures are unchanged.
