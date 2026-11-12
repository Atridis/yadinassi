# One database UI entry

Installed package, `python -m yadinassi`, and the standalone executable use the
same first-argument dispatcher:

```console
yadinassi --ui --f db/demo.sqlite --open-browser
python -m yadinassi --ui --f db/demo.sqlite
```

`--ui` uses the original XML/BSL already retained in the database. No external
configuration folder is needed. It does not create, activate, migrate or convert
the database. `--catalog-ui` and the `yadinassi-catalog` console alias are removed;
the catalog editor is still selected for admitted catalog-only/demo databases.
Plain invocations continue to run BSL. A `--ui` string inside `-c`, after a BSL
filename, or after `--` does not switch modes.

## Closed routes, not an arbitrary configuration runner

The backend returns one immutable launch snapshot inside one owned read lease.
Database UUID, generation, exact profile, schemas and actual source bytes/hashes
must agree with canonical admission. The marker or filename alone grants nothing.
For historical plain catalog profiles that never stored an executable-source grant,
this validates the current canonical metadata; it cannot reconstruct a historical
comment-only edit. The launch binding still detects source changes between the
parent and child snapshots. No new persisted marker is invented.

Existing demo/catalog-only databases open the bounded catalog editor. Explicit
catalog-object, application/CommonModules, document-object, mixed business,
reference and posting-forms grants open their existing configuration application.
`--form DECLARED_NAME` optionally selects an initial declared form. No profile
switch is exposed by this database launcher.

Raw posting format 13 without the forms grant, accumulation format 14, raw
reference accumulation format 15, inactive archives and unknown profiles are
refused. A storage/BSL feature is not automatically a browser UI capability.
The separately admitted `accumulation-reference-forms-v1` marker opens its exact
inventory forms host: Products/Warehouses and Receipt/Issue editing/posting,
with read-only saved movements, balance and turnovers. The old core15 marker
does not gain this authority and is never rewritten by the launcher.

Source files are materialized into a private, bounded temporary directory and
removed on normal exit/failure. The child checks the same database UUID,
generation, profile and full source again before constructing the application.
Source changes or a different file at the same path are refused, not adopted.
Source canonical validation does not execute BSL. Once admitted, the existing
application's explicit startup and form events run normally; no extra transaction
or root authority is granted to form modules.

A per-launch URL is local and private. Browser launch remains opt-in. Existing
single-writer attachment/reconnect and dirty/uncertain-state close restrictions
remain intact. Closing a tab does not silently discard unsaved fields. Forced
process termination or a crash is not durable draft recovery; temporary source
copies may need ordinary operating-system temporary-file cleanup after a crash.

## Source development remains explicit

`--configuration-ui CONFIGURATION_DIRECTORY` remains a source-development entry,
with its existing explicit source-profile flags. Without a database it supports
bounded declared forms and in-memory state, not persisted catalog/document work.
`--form-ui PACKAGE_DIRECTORY` remains the explicit fixed host-package route.
Neither is selected by guessing a database's contents or granting new authority.


## Acceptance scope

The existing reviewed five-flow document Chromium acquisition now starts
`python -m yadinassi --ui --f OWNED_DB`, without an external source directory or
profile flag. Its original sandbox, ownership checks, 180-RPC cap, five scenarios
and read-only typed SQLite audits remain unchanged. Package smoke exercises the
same `--ui` route for the catalog editor. These are host/UI acceptance checks,
not new native 1C semantics or proof of the future inventory UI grant.
