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

## Restricted source execution

The source-only host implements a **Boolean-only, synchronous subset** of
`SetSafeMode` / `SafeMode` (and their Russian aliases). Each routine owns its
nested enable count. A callee cannot disable a caller's restriction, and its
own enables are removed on return or failure. Dynamic `Execute` and `Eval`
fragments inherit restrictions but use a separate counter frame, so they cannot
release the caller's restriction. These source-host rules are not a claim of
complete native SafeMode compatibility or a sandbox for hostile Python code.

Restricted execution denies filesystem and network effects at their actual
operation boundary, including reads/writes using a handle opened before entry,
HTTP body-file reads, ZIP extraction and deferred JSON/XML output. Pure in-memory
operations and cleanup of resources remain available. Files already read into
memory are not retroactively erased. Unrestricted source execution retains the
normal host capabilities; merely loading a source package does not enable this
mode automatically.

String security profiles, privilege changes, asynchronous or cross-context
transfers from an active restricted frame are unsupported and fail explicitly.
The source host does not grant native server privileges or emulate a managed
client's no-op setter. Counter state belongs to one live application and execution
context, not a process-wide flag. The platform reference informed the design;
a native parity witness has not been run for this subset.

## Fresh scalar constants storage

For an explicit storage-backed startup experiment, create a **new**, separately
owned SQLite artifact:

```sh
yadinassi --configuration-source path/to/xml --run-startup --source-scratch-db owned-directory/constants.sqlite
```

The destination must not already exist. Its parent must be an existing owned,
non-symlink directory (with no group/world write permissions on POSIX). This
constants-only profile is bound to the entire source digest, configuration UUID
and admitted scalar declarations. It does not open, migrate or grant access to an
existing application database and cannot be combined with `--f`. The resulting
file is retained after success or failure for inspection; this experimental path
currently has no reopen command. Do not treat it as a complete configuration DB.

`Constants.<Name>.Get()` and `.Set(value)` (and Russian aliases) operate on real
SQLite values in the synchronous server-side source family. Supported storage
values are exactly validated String, Number, Boolean and Date declarations.
Unsupported declared types fail by name. Writes with unsupported constant-module
hooks, data-history or validation policies fail rather than bypassing them.
Only explicitly measured fresh String defaults are initialized in SQLite.
For unmeasured declarations, `Get()` before an explicit `Set()` reports an
uninitialized constant. The measured cases and provenance are listed below. Closing the application invalidates its managers.
Source SafeMode rejects access to this database just like other external I/O;
this is a conservative host restriction, not claimed native database parity.

## Source enumeration values

The source host exposes declared enumeration values through `Enums` /
`Перечисления` using the existing immutable enum runtime. Metadata UUIDs and
value declaration order determine identities; no values are synthesized from
names. Each source application owns one reference/type snapshot, shared by its
modules and by `Type`, `TypeOf` and enum `TypeDescription` lookup. This capability
needs no database and grants neither storage serialization nor native type GUID
conversion.

Rich source metadata remains preserved even when an enum's runtime declaration
is unsupported; accessing that enum reports the specific limitation. Manager
module execution, forms and arbitrary metadata services are not implied by
availability of an enum's declared values.

`Metadata.Languages` exposes declared language metadata and its actual
`LanguageCode`. `Metadata.DefaultLanguage` resolves the XML reference to that
same declared metadata object; an absent, malformed or undeclared reference is
an error, not a guess based on the host locale or the first language in a list.


### Measured fresh String defaults

A fresh `String(64, Variable)` constant, without unsupported write policies, is
initialized to the empty string in the source constants database. Native 1C
8.3.27.1508 confirmed initial Get, its String type and zero length, followed by
Set/Get roundtrip in an owned disposable database:
[run 43309356636](https://github.com/Atridis/yadinassi/actions/runs/43309356636),
source `f3cd1ca0925a22baa4c9ef6ceedbaedeba174223`.
This observation does not establish defaults of other scalar types, fixed-length
strings, or unmeasured length qualifiers. No startup callbacks are skipped to
manufacture a successful Get.

### Source manager modules

The source-only synchronous server can lazily call exported BSL routines from
catalog, document, report and data-processor `Ext/ManagerModule.bsl` files.
Both English and Russian namespace names are accepted. An unused module is not
compiled; a reached unsupported statement reports its original module location.
This does not activate database managers, CRUD, object modules or client/server
transport. Missing manager source and unavailable platform operations fail
explicitly. Manager initialization statements, asynchronous execution and direct
qualified calls with omitted arguments remain outside this first runtime slice.
A manager receiver is not mislabeled as a common-module platform type.

Global common-module exported routines are resolved on the current execution
side after local routine/value and built-in function bindings. Duplicate exported
names fail explicitly; source loading grants neither privileged execution nor
cross-side calls. Global modules remain unavailable through named-module access.
Their exported names are indexed on the first unresolved call, without executing
module initialization. Global return-value reuse is explicitly unsupported,
rather than silently ignored. Named common-module reuse retains its existing
implementation. These source-host checks are not a native compatibility claim.

### Scratch extension inventory

A newly created source scratch database now has a versioned, source-bound empty
extension registry and application-issue registry. Server-only read operations
`ConfigurationExtensions.Get()` and `GetSessionApplicationIssuesInformation()`
read that actual registry. Database, SessionApplied and SessionDisabled select
that host's empty extension state; none of them inspects another database.
Missing tables, changed binding, or populated registry fail explicitly. There is
no attachment, activation, mutation, filter evaluation, or implicit scratch
creation. Existing databases are never opened or migrated. SafeMode blocks the
read. The API shape follows the platform reference; this is not full native
extension support or proof that a loaded configuration has no required extensions.

Source session parameters accept exact `v8:FixedStructure` declarations and
actual FixedStructure assignments in addition to scalar and FixedMap values.
They retain the same owning-server-family and lazy-initialization rules; an unset
value remains an error. Unknown types and unsupported collection TypeDescription
queries remain explicit errors.

Source-only String declarations may use `Length=0` with Variable allowed length.
Assignments are bounded to 1,048,576 UTF-16 code units as a host resource limit,
not truncated to that length. This opt-in does not expand the legacy database
profile parser or invent an empty string default.

The source scratch host exposes its own stable synchronous session identity via
`GetCurrentInfoBaseSession()`. `GetBackgroundJob()` reports the real foreground
origin as Undefined, as specified by the platform API for non-background
sessions. It does not invent a native session number, user, authentication state
or a native InfoBaseSession TypeOf identity. Those properties remain unavailable.
Calls require the live owning server family and an explicitly created scratch
database. Closed, foreign, client and asynchronous contexts are rejected.

`Metadata.ScriptVariant` reads the declared XML value and exposes an opaque
English/Russian identity, comparable with the read-only property domain
`Metadata.ObjectProperties.ScriptVariant` by member name or string index. The
runtime never assumes English from source code spelling. Missing, structured or
unknown XML values and unsupported property domains fail explicitly. Native
presentation and TypeOf identity are not yet claimed by this source facade.

### Explicit compatibility experiments

`--source-compatibility-target X.Y.Z.W` is an opt-in source-startup experiment.
It makes source `SystemInfo.AppVersion` report the selected compatibility target,
not an installed 1C:Enterprise version. Without that option AppVersion fails
explicitly. The CLI prints the target and actual yadinassi version separately,
with a warning that this is neither native 1C nor a compatibility guarantee.
`SystemInfo.YadinassiVersion`, `CompatibilityTarget` and `IsCompatibilityTarget`
are explicit source-host introspection properties; they are not native 1C API
claims. Other unimplemented system properties remain errors. No target is selected
implicitly from the XML or host OS, and existing database/profile modes do not
accept this option.

`Metadata.CompatibilityMode` likewise preserves its admitted XML enum identity;
DontUse is never inferred from the selected experiment target. Supported values
are DontUse, Version8_1, Version8_2_13/16 and Version8_3_1 through Version8_3_24.
This only exposes source metadata: it does not implement version-dependent native
platform behavior. String conversion deliberately returns the canonical XML token
(for example Version8_3_24), not a claimed native localized presentation. Code
that depends on exact native enum display text can therefore behave differently;
the experimental CLI warning calls out this boundary. Unknown values still fail.
The official syntax-reference inventory used for this slice lists modes through
8.3.23. The 8.3.24 source token is retained from an actual XML declaration; the
existence of that compatibility mode is also documented in the vendor's
[release notes](https://v8.1c.ru/upload/static/new-contracts-1_0_7.pdf). This is
source-admission evidence, not a native runtime witness for enum presentation.
