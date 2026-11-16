# Source document date-window selection

`Documents.Name.Select/Выбрать(start, end)` now accepts zero, one or two
arguments in the explicit source-document profile. Bounds are exact, known BSL
Dates or Undefined (unbounded). Both endpoints are inclusive, including the time
component; there is no implicit start/end-of-day conversion. Reversed periods,
unknown boundary dates, other types and extra arguments are rejected before
record reading. The no-argument form is unchanged.

The existing reader first validates its complete bounded snapshot, then the
source host filters by Date. An out-of-range corrupt record or excessive record
count is not hidden by the filter. This is not a database index or unbounded
query capability. Original identity ordering is retained, not promised as native
chronological order. Posted and deletion-marked records are not newly filtered.

Selection membership and scalar fields are a read snapshot. GetObject continues
to use the existing lifecycle path (including fresh section/OnRead loading where
required). Existing transactions retain their own uncommitted visibility, and
all owner, safe-mode, synchronous and poisoned-lifecycle guards are unchanged.
No modules are initialized merely to filter dates, and no data is written.
These tests are source-host evidence, not new real-1C parity.
