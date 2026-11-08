# Local SQLite catalog database

This is yadinassi's own storage format, implemented using Python's standard-library `sqlite3`, not a native 1C file-format adapter. No external SQL server or ORM is required. Official configuration XML and BSL module files are the configuration interchange. A separate, explicitly invoked offline maintenance API migrates this project’s own SQLite v1 storage to v2; it does not import native 1C database files.

## Explicit modes

- No database flag: ordinary BSL script execution, no database or server selected or created.
- `--f application.sqlite`: local thick/runtime mode against an **existing** SQLite file. Missing files refuse; opening never creates a database.
- `--create-db application.sqlite --import-xml configuration-directory`: explicit creation of a new database, with configuration files and normalized schema imported atomically. Cannot be combined with script execution, `-c`, or `--f`; existing files are never overwritten.
- Add `--inactive` to archive a configuration without activation. Original XML and module bytes persist and can be exported by the host API, but data reads/writes and Interpreter activation refuse. Activation issues are reported; unsupported code is never silently skipped or executed by import.

These import flags are yadinassi commands, not native 1C CLI syntax. Future client-only/server-only modes have not been implemented or assigned flag names. Local mode does not secretly launch a loopback server. Future remote clients would call an application service; they would not open a shared SQLite file.

Example:

```sh
python -m yadinassi --create-db application.sqlite --import-xml ./configuration
python -m yadinassi --f application.sqlite -c 'O=Catalogs.Products.CreateItem(); O.Code="10"; O.Description="Example"; O.Write();'
python -m yadinassi --f application.sqlite -c 'Message(Catalogs.Products.FindByCode("10").Description);'
```

Use names/required field values from your admitted configuration. Unsupported configurations fail rather than promise arbitrary application compatibility. Initially supported: flat string-code catalogs, explicit codes, Description, and bounded String/Number/Boolean/DateTime/fixed catalog-reference attributes. Nonempty required application/object modules and unsupported metadata behaviors prevent activation. Their source may be archived with `--inactive`. General configured-module execution, arbitrary data import, and Documents/register adapters are not claimed by this storage increment.

## Persisted application

The database stores its format marker, logical database UUID, configuration generation/activation state, exact accepted XML/BSL bytes with hashes, normalized catalog schemas, typed catalog records, opaque revisions and commit receipts. Version 1 stores row attributes in tagged JSON. Version 2 stores attributes in individual typed columns; the same closed tagged codec remains in use for canonical write intents and receipt compatibility. Neither representation is a native serialized value format. Exact Decimal text never passes through binary float; dates are timezone-free whole-second calendar values, including year 0001. References retain database/catalog/record identity, including typed empty UUID. Undefined/Null are not implicitly mapped from SQL NULL or admitted into fixed fields.

The SQLite connection and catalog operations remain in `sqlite_catalog.py`; the physical-name registry and offline v1 migration are in SQLite-specific modules. `catalog_backend.py` exposes immutable logical schema/card/key/revision types and bounded operations. Runtime owns BSL CatalogObject semantics, UI owns edit/navigation state, and backend owns consistency and persistence. PostgreSQL and MongoDB are future adapter targets only: no dependencies or claimed engine support. Unsupported ordering/filter/transaction capabilities must refuse, not silently change behavior. Default catalog selection has an explicit limit and code/identity order; overflow refuses rather than displaying a truncated total. Typed scans support explicit ordering. These orders are not a claim of native collation parity.

String and Decimal metadata [qualifiers are applied on assignment](catalog-qualifier-assignment.md), and direct backend create/update calls use the same conversion before SQL and receipt construction. Storage decoding remains strict and never converts persisted corruption into an accepted value. Code uniqueness applies to the converted code. This does not add fixed strings, new scalar types, UI behavior or general native catalog parity.

## Transactions and failures

Connections explicitly disable implicit Python transaction creation (`isolation_level=None`); writes use `BEGIN IMMEDIATE`, `COMMIT` and `ROLLBACK`, compatible with Python 3.10. Foreign keys are enabled per connection. Initial policy is rollback journal `DELETE`, synchronous `FULL`, one active view/writer per backend instance, and bounded busy waits. Read-only host openings use an internally constructed `mode=ro` URI and `query_only`; callers cannot inject URI options.

An update checks its opaque expected revision inside the write transaction; duplicate code, stale edits and cross-database references refuse. This revision is not native DataVersion. Cancel/discard does not call Write. Successful Write clears new/dirty state only after a confirmed receipt. An uncertain COMMIT response preserves the exact pending intent, blocks further mutation, and resolves the persisted operation receipt before any retry. A mismatch refuses rather than replaying a different create.

Host transactions containing several successful writes can resolve the complete
ordered batch through the [batch receipt recovery contract](catalog-batch-receipts.md).
It preserves original revisions and, where supported, generated codes without
replaying writes or reading a later card as the original outcome.

Process termination before commit and after commit is tested with real temporary SQLite files; reopening observes the old or committed state and a matching receipt. This does not prove universal power-loss durability on every filesystem or hardware device. SQLite owns recovery/journaling; do not remove its journal or copy only a live main file. No network filesystem or native concurrent-writer compatibility is claimed.

Initial host authority is a local, host-selected regular file under an owned directory (POSIX rejects group/world-writable parents and foreign ownership). Symlink/reparse ancestors and hardlinked database files refuse. macOS’s verified OS-owned `/var` and `/tmp` aliases are normalized before those checks; Windows case/8.3 spelling is canonicalized only after every directory component passes no-link admission. This is **not** protection against a malicious process running as the same OS user or a portable Windows ACL proof. Keep application files in a private local directory. The renderer cannot select database paths or submit SQL.

Bounds include 2,048 configuration files, 1 MiB per source file, 16 MiB total configuration, up to 512 catalog schemas, 64 attributes/catalog, 10,000 records/catalog and transaction changes, a 1 MiB canonical write-intent row payload, and a 256 MiB database ceiling. Legacy v1 reads may admit JSON up to 1 Mi characters; v2 point reads bound the corresponding UTF-8 fields to 4 MiB plus bounded system-column overhead. Aggregate scans remain bounded to 16 MiB. Other metadata and filesystem limits can refuse a configuration before these maxima are reached. XML directory traversal is bounded and rejects symlinks, special files, arbitrary path aliases, DTD/entities and changed source files. Schema activation is all-or-nothing.

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
outcomes, not assumed native concurrency guarantees. The source-bound lane has produced bounded results, including [this independently reviewed run](https://github.com/Atridis/yadinassi/actions/runs/41663986227); it does not establish general application or metadata parity.

## Typed catalog scans (Query v1 preparation)

Each read, selection or scan parses its catalog schema once in the pinned
transaction. Scans no longer construct every full card before filtering.
`scan_catalog_values(catalog_id, request, fields)` returns explicit
`CatalogValueRow` projections in requested field order; it never represents
unloaded tabular sections as empty sections. Query and exact Find use this
scalar contract and never read section tables.

The backend port accepts typed bounded predicates, ordered field identities and
explicit projection fields, not SQL, connections or callbacks. On v2/v3, SQLite
applies the typed predicate, ordering and page limit. Private connection-local
collations implement Python `casefold_v1`, exact Decimal comparison and UUID
integer comparison; SQLite numeric coercion and ASCII `NOCASE` are not used.
Empty references compare as the zero UUID, including inequality. The legacy v1
JSON storage path retains bounded Python filtering and ordering, including its
historical stable source order for UUID aliases.

A catalog-wide bounded streaming pass still validates owner scalars before SQL
selection. This intentionally preserves rejection of corrupt values outside a
filter without retaining their payloads or cards. It is not an index-only lookup:
existing catalog-wide count/16 MiB limits and integrity validation still cost a
scan. Full-card scans also stream section integrity checks in bounded owner
batches, but count nested-result budgets only for matching owners. They attach
sections only to the returned page. Scalar projections deliberately have no
section-integrity or nested-result-budget dependency; obtaining a full object
still validates and loads its complete sections.

A read view pins one SQLite transaction snapshot. Each view supports one active
traversal. Opaque single-use continuation tokens bind the view, complete request,
projection fields and full-card/scalar mode. Starting another traversal
invalidates the old token. v2/v3 cursors retain an offset, not all result cards;
continuation pages read the same pinned snapshot. Equal order keys retain UUID
integer tie-breaking, including previously admitted parseable UUID spellings.

Pages contain at most 1,000 rows; the 10,000-record catalog limit remains.
Same-snapshot aggregates reject owner scans exceeding 16 MiB of text plus fixed
row overhead before payload validation, independently of page size/selectivity.
Full-card scans preflight per-owner and whole-filtered-result section budgets
before any section payload is read, including when the first page is smaller
than the complete result. Predicate limits remain 64 nodes/depth 8 and 16 order
terms. Exact numeric operands remain bounded before coefficient expansion.

Default `codepoint` preserves exact Find behavior; Query requests versioned
`casefold_v1`. Neither claims native regional collation or changes write
uniqueness. Native evidence still covers only the owned ASCII case-pair fixture;
broader comparison tests establish this implementation contract.

Measured statement counts and their scope are recorded in
[catalog scan cost and integrity boundaries](catalog-scan-performance.md).

`FindByCode` and exact `FindByDescription` use typed predicates across the complete
admitted catalog, not a first-1,000-row window. Ambiguous description matches still
refuse. This change does not silently expand ordinary catalog selection limits.

Query parser/runtime and native output-only comparison remain under development;
local SQLite tests are not native query compatibility evidence. Reference cursor
values are supported, while reference-projection `Unload` and result-column metadata
remain explicit unsupported surfaces until truthful dynamic descriptors are admitted.

## Flat catalog deletion marks

For admitted flat, ownerless catalogs, `DeletionMark` / `ПометкаУдаления`
is a Boolean in a detached object. Assignment is buffered; `Write` persists it
along with other edits. Ordinary reads, selections and Query expose the stored
mark. A mark does not delete a record or invalidate references. Optimistic
revision conflicts and commit-receipt recovery use the same rules as other
writes. After an uncertain response, call `Write` to resolve the exact pending
intent before changing the object. A failed write leaves its edit buffer intact.

`SetDeletionMark` / `УстановитьПометкуУдаления` remains unsupported. Two
source-bound native acquisitions on platform 8.3.27.1508 observed successful
property assignment and Write, but SetDeletionMark(True) raised an exception
for existing and new objects, with both Read/Insert/Update rights and an
additional Delete grant. The exception cause was not captured and must not be
inferred from those two runs; their bootstrap baselines were independently
created. A third finite diagnostic matched neither its rights, lock nor
method-missing patterns; this does not exclude those causes. See the [first
observation](https://github.com/Atridis/yadinassi/actions/runs/41645005336),
[Delete-right observation](https://github.com/Atridis/yadinassi/actions/runs/41647274341)
and [finite diagnostic](https://github.com/Atridis/yadinassi/actions/runs/41649545810).

`!todo`: understand the observed method failure and measure its return, writes,
permissions and error semantics before exposing the method. Physical deletion,
cascading marks for hierarchical/owned catalogs and module/event semantics need
separate contracts; these metadata profiles cannot currently activate. The
[official platform description](https://1c-dn.com/library/using_the_deletionmark_field_of_a_database_object/)
distinguishes direct assignment and the method's additional actions.

## Catalog storage and maintenance

New owned SQLite databases use an individual table for each catalog and individual columns for its attributes. Names, identity mapping and the limitations of legacy migration are described in [SQLite catalog layout v2](sqlite-catalog-layout-v2.md). Catalogs with admitted sections use the [v3 tabular-section storage contract](sqlite-catalog-sections.md) and [bounded XML/BSL adapter](catalog-tabular-sections.md). UI editing of such schemas remains unsupported.

The migration API requires all old processes stopped and prevented from reconnecting, a verified backup, sufficient disk space and a trusted owned directory. `prepare_v1(path, maintenance=True)` returns a plan that must be saved outside the database before `migrate_v1(path, plan, maintenance=True)`. If the outcome is `uncertain_commit`, keep that exact plan and use `resolve_migration(path, plan, maintenance=True)` while maintaining exclusive access. Never blindly retry. The resolver is read-only; a hot rollback journal can require SQLite recovery under maintenance before a definite result is possible. The API does not itself create a backup or stop other processes. It declines unexpected schema objects or explicit third-party indexes instead of silently dropping them.

# Creation failure safety

Database creation preserves a reserved destination after failure, including an
uncertain COMMIT. See [creation failure boundary](sqlite-catalog-create-failure.md)
before retrying or removing a failed destination.

