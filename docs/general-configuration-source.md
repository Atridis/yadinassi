# General configuration source and startup attempt

General source admission is separate from activation of a supported database
schema. It accepts an ordinary Designer XML directory, preserves metadata from
all families and retains BSL and opaque resource bytes. An unknown type, property,
module, or binary resource does not silently disappear and is not represented as
an operational table or successful no-op.

Import does not compile or run modules. The report lists metadata families, the
whole-source digest, and the fact that storage has not been activated. Syntax and
runtime support are checked by a separately requested startup attempt. A startup
error does not invalidate the saved source package. This is not a declaration of
full configuration compatibility or a migration of an existing database.

## Preservation

The source archive contains `manifest.json` and the original files under
`source/`, with SHA-256 checksums. The loader verifies every byte, refuses missing
or additional files, and rebuilds metadata inventory instead of trusting saved
runtime permissions. No archive member is extracted to the filesystem. Saving is
exclusive-create: an existing archive, SQLite database, or other file is never
overwritten. An interrupted write can leave a partial new archive; verify it
with the loader before using or distributing it.

The ordinary source-directory reader retains its original small limits. General
admission uses explicit bounds of 50,000 files, 32 MiB per file, 512 MiB total,
32 directories of depth, and 250,000 XML elements per file. XML must be well-formed
UTF-8 with no DTD or entity declarations. Unsafe/colliding paths, links and
changing source files are rejected. These are resource/integrity protections,
not lists of supported business functions.

## Compatibility boundary

Existing closed source profiles, SQLite grants and validation stay unchanged.
General-source admission alone never allows use of an existing database,
activation of unsupported metadata, or writes through a guessed schema. The
source package is not a native `.cf` or `.dt` file and is not a database backup.

## CLI

Inspect a complete exported directory, optionally saving a portable package:

```sh
yadinassi --configuration-source path/to/xml --save-source configuration-source.zip
```

Explicitly attempt startup from a directory or saved package:

```sh
yadinassi --configuration-source configuration-source.zip --run-startup
```

This source-only path is opt-in and does not take `--f` or create an ordinary
SQLite database. Startup is headless, not a UI session. It uses the existing
interpreter's standalone preprocessor context (other profiles are currently
refused on this path) and does not claim native client/server or file-mode parity. Reached unsupported services
fail visibly; a successfully admitted package may fail to start. Common modules
are compiled when reached instead of rejecting the entire package because an
unused module contains unsupported syntax. The regular database-backed UI and
exact-profile commands continue to use their existing admission rules.

## Source-only session state

Source startup binds its own live interpreter family to the existing typed
session store. Scalar declarations reuse the closed qualifier parser. A single
`v8:FixedMap` declaration accepts a real `FixedMap` runtime value, not a mutable
`Map` or an untyped placeholder. Other declared types fail on access instead of
blocking source preservation. This does not grant database access, privileges,
remote transport or a generic TypeDescription for collection types.

Uninitialized values remain unset. A server read invokes the actual session
initializer with the requested names; if no value is assigned, the read fails.
There is no invented empty-map default. Client/foreign-family/closed-session
access and recursive initialization remain rejected. Values belong to one
application lifetime, not a shared global store.


`CurrentRunMode()` / `ТекущийРежимЗапуска()` reports `Undefined` in this
source-only headless host: it is neither an ordinary nor a managed client
application. It does not infer a native client mode from the name of the BSL
module, Python's OS or compilation-side flags. The host binding expires with
its application; it grants no UI or client transport.

The API contract was checked against the official EDT 2026.2 platform reference,
[`platform.doc` 3.0.1.v202610261959](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar),
`Global_context/methods/catalog33/CurrentRunMode3920.html`. This is documentation
and explicit host-policy evidence, not a new measured native runtime result.

Source common modules can use the existing bounded `DuringSession` and
`DuringRequest` value cache for qualified same-side calls. Session caches are
application-owned; request caches use the interpreter's synchronous request
boundary. Refresh clears those caches, and closing the source application
invalidates their ownership. This does not enable cross-process transport,
server pools, privileged/global modules or asynchronous cached calls.

`Metadata` / `Метаданные` now exposes a read-only view of the actual source
inventory and XML `ChildObjects`, including ordered nested subsystems. Known
scalar source properties are read from XML; missing declarations, unsupported
properties and schema discrepancies are errors. This view does not activate
catalog/document managers, create tables, or manufacture an empty operational
schema. Existing closed-profile metadata and storage grants are unchanged.

The ordinary `Execute expression;` statement form reuses the existing Execute
fragment parser and safety boundaries; the parenthesized spelling stays valid.
Safe-mode/privilege APIs are not replaced with successful no-ops by this host.
