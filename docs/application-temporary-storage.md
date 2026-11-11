# Application-owned temporary storage (in progress)

This is a coherent trusted application-service block, not a database codec or
network/file storage implementation. Native scalar/collection measurement is
prepared separately; no measured compatibility is claimed yet.

The planned surface is PutToTempStorage, GetFromTempStorage,
DeleteFromTempStorage and IsTempStorageURL, with their Russian aliases. State
belongs to one explicit ConfigurationApplication generation. Addresses must not
let another application or stale interpreter access values. Closing, failing or
cancelling an application releases storage. Independent server activations in
one application share it; standalone interpreters do not gain ambient storage.

Stored values use bounded immutable snapshots. Successful retrieval returns a
fresh value, and failed capture/replacement must preserve the prior entry.
Aggregate quotas bound retained binary/text/node state, not just individual
objects. Existing ValueStorage-compatible scalar/collection shapes are reused;
unsupported references and authority-bearing objects remain rejected.

Native observation covers exact scalar/collection roundtrips, copy isolation,
replacement, deletion, stale addresses, missing/invalid address behavior and
optional owner argument forms. Generated native addresses never enter artifacts.
Form-owner lifecycle and cross-event expiry of ownerless values require separate
evidence and will not be guessed from a single-call observer.
