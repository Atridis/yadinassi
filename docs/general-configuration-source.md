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
