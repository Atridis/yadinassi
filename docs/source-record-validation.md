# Independent bounded record validation

Catalog/document validate_records now rejects a MAX_RECORDS+1 row itself, not
only through a preceding storage preflight. The existing bounded SQL query is
retained and the extra row is rejected before decoding. Cursor cleanup is
explicit on success and on any validation or count failure.

Canonical nonzero record UUID and exact integer revision validation is shared
between full validation and selection. UUID text is parsed once per record,
then reused in returned selections instead of parsed two or three times.
Lowercase canonical spelling, nonzero identity, and inclusive revision bounds
1 through 2**53 remain unchanged. SQLite's schema and preflight checks remain.

Tests directly invoke validation without preflight, exercise both record-limit
boundaries, identity/revision rejection cases and one-parse counts. Retained
exception tracebacks do not prevent a second connection from committing after
validation failure. No measured runtime speedup or native parity is claimed.
