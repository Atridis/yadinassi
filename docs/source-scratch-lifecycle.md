# Source-bound scratch database lifecycle

This experimental host persists admitted source files (XML, BSL and resources)
and the supported scalar constants in a private SQLite file. It is **not** a
native 1C database or activation of arbitrary configuration data objects.
Unsupported capabilities still fail explicitly when accessed.

Create once:

```sh
yadinassi --configuration-source source.zip --run-startup --source-scratch-db scratch.sqlite
```

Reopen explicitly with the exact same source package:

```sh
yadinassi --configuration-source source.zip --run-startup --open-source-scratch-db scratch.sqlite
```

Creation never overwrites a file. Reopen never creates a missing file and does
not migrate a normal database, a previous scratch format, or changed source.
The v3 format stores all source bytes for integrity checking; this does not
execute those bytes. Startup remains a separate explicit operation. Copying
source files into the DB does not imply support for their metadata or services.
No source extraction CLI or automatic configuration update is supplied yet.

Reopen checks exact schema (including absence of extra triggers/views/indexes),
source identity and bytes, constant definitions and encoded values, and empty
extension state. Unsupported scalar defaults remain uninitialized except for
already measured cases. Files must be regular, non-symlinked, singly linked,
privately writable files in an approved private directory. Windows reparse
points are refused. File identity and schema/source binding are rechecked on
access. This is corruption/misuse detection, not protection against a hostile
process with the same OS account and arbitrary filesystem access.

An old v2 scratch file is deliberately refused; preserve it for inspection.
Do not rename an ordinary database to use this command. Use a new scratch file
for changed source until a separately designed migration capability exists.
