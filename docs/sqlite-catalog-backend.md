# Local SQLite catalog database

This is yadinassi's own storage format, implemented using Python's standard-library `sqlite3`, not a native 1C file-format adapter. No external SQL server or ORM is required. Official configuration XML and BSL module files are the configuration interchange; data migration is not implemented.

## Explicit modes

- No database flag: ordinary BSL script execution, no database or server selected or created.
- `--f application.sqlite`: local thick/runtime mode against an **existing** SQLite file. Missing files refuse; opening never creates a database. The GUI bridge remains a read-only catalog browser in this increment.
- `--create-db application.sqlite --import-xml configuration-directory`: explicit creation of a new database, with configuration files and normalized schema imported atomically. Cannot be combined with script execution, `-c`, or `--f`; existing files are never overwritten.
- Add `--inactive` to archive a configuration without activation. Original XML and module bytes persist and can be exported by the host API, but data reads/writes and Interpreter activation refuse. Activation issues are reported; unsupported code is never silently skipped or executed by import.

These import flags are yadinassi commands, not native 1C CLI syntax. Future client-only/server-only modes have not been implemented or assigned flag names. Local mode does not secretly launch a loopback server. Future remote clients would call an application service; they would not open a shared SQLite file.

Example:

```sh
python -m yadinassi --create-db application.sqlite --import-xml ./configuration
python -m yadinassi --f application.sqlite -c 'O=Catalogs.Products.CreateItem(); O.Code="10"; O.Description="Example"; O.Write();'
python -m yadinassi --f application.sqlite -c 'Message(Catalogs.Products.FindByCode("10").Description);'
```

Use names/required field values from your admitted configuration. Unsupported configurations fail rather than promise arbitrary application compatibility. Initially supported: flat string-code catalogs, explicit codes, Description, and bounded String/Number/Boolean/DateTime/fixed catalog-reference attributes. Nonempty required application/object modules and unsupported metadata behaviors prevent activation. Their source may be archived with `--inactive`. General configured-module execution, data migration, Documents/register adapters and UI editing/saving are not claimed by this storage increment.

## Persisted application

The database stores its format marker, logical database UUID, configuration generation/activation state, exact accepted XML/BSL bytes with hashes, normalized catalog schemas, typed catalog records, opaque revisions and commit receipts. Row attribute payloads use a closed tagged JSON encoding inside SQLite TEXT; this is our encoding, not a native serialized value format. Exact Decimal text never passes through binary float; dates are timezone-free whole-second calendar values, including year 0001. References retain database/catalog/record identity, including typed empty UUID. Undefined/Null are not implicitly mapped from SQL NULL or admitted into fixed fields.

The SQL schema and connection remain inside `sqlite_catalog.py`. `catalog_backend.py` exposes immutable logical schema/card/key/revision types and bounded operations. Runtime owns BSL CatalogObject semantics, UI owns edit/navigation state, and backend owns consistency and persistence. PostgreSQL and MongoDB are future adapter targets only: no dependencies or claimed engine support. Unsupported ordering/filter/transaction capabilities must refuse, not silently change behavior. Current catalog scans have an explicit limit and code/identity order; overflow refuses rather than displaying a truncated total. This order is not a claim of native collation parity.

## Transactions and failures

Connections explicitly disable implicit Python transaction creation (`isolation_level=None`); writes use `BEGIN IMMEDIATE`, `COMMIT` and `ROLLBACK`, compatible with Python 3.10. Foreign keys are enabled per connection. Initial policy is rollback journal `DELETE`, synchronous `FULL`, one active view/writer per backend instance, and bounded busy waits. Read-only host openings use an internally constructed `mode=ro` URI and `query_only`; callers cannot inject URI options.

An update checks its opaque expected revision inside the write transaction; duplicate code, stale edits and cross-database references refuse. This revision is not native DataVersion. Cancel/discard does not call Write. Successful Write clears new/dirty state only after a confirmed receipt. An uncertain COMMIT response preserves the exact pending intent, blocks further mutation, and resolves the persisted operation receipt before any retry. A mismatch refuses rather than replaying a different create.

Process termination before commit and after commit is tested with real temporary SQLite files; reopening observes the old or committed state and a matching receipt. This does not prove universal power-loss durability on every filesystem or hardware device. SQLite owns recovery/journaling; do not remove its journal or copy only a live main file. No network filesystem or native concurrent-writer compatibility is claimed.

Initial host authority is a local, host-selected regular file under an owned directory (POSIX rejects group/world-writable parents and foreign ownership). Symlink ancestors and hardlinked database files refuse. This is **not** protection against a malicious process running as the same OS user or a portable Windows ACL proof. Keep application files in a private local directory. The renderer cannot select database paths or submit SQL.

Bounds include 256 configuration files, 1 MiB per source file, 16 MiB total configuration, 128 backend catalog schemas (the XML importer admits fewer), 64 attributes/catalog, 10,000 records/catalog and transaction changes, 1 MiB encoded row payload, and 256 MiB database ceiling. XML directory traversal is bounded and rejects symlinks, special files, path aliases, DTD/entities and changed source files. Schema activation is all-or-nothing.

## Compatibility evidence boundary

SQLite persistence and rollback correctness are established by owned SQLite tests. Native Docker remains a strictly single-session BSL/form behavior reference using official XML tooling and textual results only. New writable catalog behavior still requires its separate source-reviewed native observation packet; local tests alone do not establish every native method/error/validation semantic. Old native database-format fixtures are not used as a SQLite storage specification.

The XML directory reader assumes a stable, host-owned source directory while importing.
It rejects symlinks/special files, bounds directory enumeration and verifies each opened
file's identity/content size before and after reading. This is not a descriptor-anchored
sandbox against a hostile same-user process concurrently replacing ancestor directories.

## Official behavior oracle

The new `catalog-object-behavior-v1` lane creates an owned disposable configuration
using official Designer XML import/export, then runs 24 scalar BSL observations in one
ENTERPRISE action session. Bootstrap, compilation and action sessions are sequential;
no overlapping native sessions or database-format inspection occurs. Its temporary
platform database is opaque to yadinassi.

The comparator uses an explicitly authored SQLite logical reference configuration with
the same bounded catalog behavior profile. It labels its scope
`owned-catalog-object-logical-reference-model` and sets
`metadata_import_parity_claimed=false`. Full Designer XML activation is not inferred
from method-output parity. Duplicate-code and stale detached-object writes are measured
outcomes, not assumed native concurrency guarantees. Actual native results remain
pending until the source-bound lane runs and is independently audited.
