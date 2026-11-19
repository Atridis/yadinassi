# Lightweight Table sorting and historic order

Blocking `test_native_target_sort` checks all 96 Python orders, record/cell/owner
and metadata preservation, numeric ordering and callback rejection. The readonly
`cells` snapshot contract is checked separately, not excused as collation.

`python -m tests.compatibility_native_table_sort` validates the unchanged fixture
and all 96 actual cases, then reports exact historic ordering differences. The
existing performance job includes this untimed report in its summary. No errors
are caught: missing coverage, fixture/data corruption and execution errors fail.
Only the final historic order comparison is informational, not a parity claim.

For the strict oracle use
`python -m unittest tests.compatibility_native_table_sort -v`.
It remains red on historical mismatches. Runtime and fixtures are unchanged.
