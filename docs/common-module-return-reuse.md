# Client common-module return-value reuse

Non-global, managed-client-only common modules admit `DuringSession` and
`DuringRequest`. Server, ServerCall, ordinary client, external connection,
privileged and asynchronous reuse remain closed. No server/client dual cache
or distributed/session-storage behavior is implied.

Qualified function calls use typed primitive or flat Structure argument keys;
unqualified self calls bypass caching and procedures execute normally.
Arguments are evaluated once. Keys describe their values before execution:
measured native scalar/Structure mutations are not replayed on a cache hit.
Returned admitted objects retain identity. Errors are not cached.
`RefreshReusableValues()` clears the application's session and current request
entries. A request is one outer synchronous scheduler dispatch, with cleanup
on success and failure; session entries survive dispatches until application
closure or invalidation. Exit handlers retain access while the family is open.

The native source-bound 16 observations are from run 43130157790 on
8.3.27.1508. Two actual client idle events establish the request boundary.
Case 9 measures repeated Undefined acceptance, not whether computation was
reused. No additional native experiment is claimed.

Local defensive limits are 256 entries, 16 MiB retention estimates, bounded
keys and closed ValueStorage snapshots used only for accounting. Aliased values
are remeasured before a hit; this is not a live-memory cap. Monotonic 20-minute
age and 6-minute idle expiry follow the official documented policy, not a new
native timing measurement.

Recovery note: these runtime bytes were reconstructed separately from public
acquisition ancestry after workspace loss. Earlier test PASS results do not
validate them. The private snapshot cost walker is temporarily local to reuse;
after pending #290 integration it may be deduplicated with the identical
storage accounting contract, without introducing a storage API or dependency.

Official reference: https://1c-dn.com/library/specifics_of_reusing_return_values/
