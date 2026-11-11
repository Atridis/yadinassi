# Application-owned temporary storage: closed UUID-owner profile

This is a coherent trusted application-service block, not a database codec or
network/file storage implementation. Native scalar/collection measurement is
completed in native run `43056863128` on 1C 8.3.27.1508. The immutable
sixteen-value fixture records the observed behavior; thirteen cases are replayed
exactly by this closed runtime profile.

The surface is PutToTempStorage, GetFromTempStorage,
DeleteFromTempStorage and IsTempStorageURL, with their Russian aliases. State
belongs to one explicit ConfigurationApplication generation. Addresses must not
let another application or stale interpreter access values. Closing, failing or
cancelling an application releases storage. Independent server activations in
one application share it; standalone interpreters do not gain ambient storage.

Native same-server-context Put/Get retain mutable collection identity: later
mutations through either alias remain visible. Immutable snapshots are used only
for bounded shape validation/accounting, never substituted as stored values.
Failed admission/replacement preserves the prior entry. Entry count is bounded;
aggregate binary/text/node budgets are checked on Put and successful Get, including
mutations through existing aliases. These are operation-time quotas, not a claim
of intercepting every external collection mutation. Delete and close remain
available to release over-budget state. Existing ValueStorage-compatible shapes
are reused; references and authority-bearing objects remain rejected.

Native observation covers exact scalar/collection roundtrips, copy isolation,
replacement, deletion, stale addresses, missing/invalid address behavior and
optional owner argument forms. Generated native addresses never enter artifacts.

The runtime requires an explicit UUID owner for new entries or an existing owned
address for replacement. Native also accepted omitted, numeric and empty-string
owners within the measured call; these forms are deliberately refused here until
their cross-call lifetime is supported. Tests assert this limitation explicitly.
Deleted addresses remain recognizable, reads return Undefined and repeated delete
is harmless. Replacing a deleted address is rejected. Invalid-address deletion is
a deferred native edge case; the local profile rejects malformed addresses before
accessing any state.
Form-owner lifecycle and cross-event expiry of ownerless values require separate
evidence and will not be guessed from a single-call observer.
