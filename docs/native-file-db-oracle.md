# Synthetic native file-database oracle, version 4

Version 4 runs the independent physical-catalog reader against the baseline
native auditor's frozen post-session image and compares only complete physical
table/field-name projections for `Справочник.NativeOracleItems`. An accepted
report carries the narrow `reader_validation=filtered_table_field_names_match`;
`native_compatibility=not_claimed` remains explicit. It does not prove row access,
field-type mappings, B-trees, runtime DB operations, general 1CD support or writes.
Local parser/BSL tests are not a native result: a fresh source-bound native run
and independent review remain required for this exact revision.

The existing 13 stages, 11 snapshots, CRUD lifecycle, opaque CF/DT summaries,
isolation and caps remain unchanged. Historical v1/v2/v3 reports retain their
historical meaning and are never upgraded into a physical-name comparison.

The original fixture contains one non-hierarchical catalog, NativeOracleItems:
Code `K1`, Payload String(32), Amount Number(9,2). The only metadata-v2 change is
Payload String(64), retaining every object/attribute UUID, role and module.
There are no registers, third-party configurations, supplied binary inputs or
production data. Native 1C is the generator and semantic oracle, not a dependency
of a future independent database implementation.

## Invocation and reviewed CI

From a clean, immutable checkout, the only supported host invocation is:

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --output native-db-oracle/report.json
```

The host requires the existing GHCR_USER/GHCR_TOKEN credentials for the approved
image pull. It removes them from the environment before external processes,
uses a private registry configuration only for login/pull, deletes it, and runs
the image without credentials. It refuses external database/config/dump paths,
legacy full-suite/client/export flags, stale output, unverified git identity,
untracked source changes, source-hash changes, or unexpected staged files.

The separate workflow `.github/workflows/native-1c-file-db-oracle.yml` runs only
when the exact owner-reviewed branch `codex/native-file-db-oracle-reviewed` is
advanced. Admission binds the owner/repository numeric IDs, sender, actor,
triggering actor, event SHA, workflow SHA, branch and immutable checkout. There
is no manual-dispatch dependency. Normal main/PR builds and the existing Async
reviewed branch do not opt into this lane. Top-level and eligibility permissions
are empty; the native job has only contents:read and packages:read. Existing
pinned actions and package credentials are reused; no authentication policy,
package visibility, or access settings are changed.

The admission checks are not a privacy boundary against a changed workflow or
the existing package grant to this public repository. Review the exact revision
before advancing the dedicated branch. This document does not authorize doing
so. The first candidate was based on main
`724ea9354f5c42772c69ffea967dfd7a070fedef`, tree
`201f76220182a9efb9f091cb664f1fca0c3ee16d`; actual execution records its own full
checkout commit/tree and exact staged source hashes, never that historical
baseline by assumption.

## Lifecycle and observations

1. Create a fresh file infobase, obtain the platform's empty XML, inject only the
   original reviewed fixture, import, apply, redump and verify it.
2. Bootstrap exactly two users. Setup has the separate bounded administrator
   role; measured catalog operations use only NativeOracleCatalogCRUD. Runtime
   code verifies the current singleton role and non-privileged execution.
3. Freeze an empty v1 baseline. Fresh-session reads and the separate admin user
   inventory/storage-name audit run on disposable clones, never the frozen bytes.
   After that audit closes, only the independent reader inspects a private frozen
   copy of its post-session image; this is not an extra lifecycle snapshot.
4. Create `K1 / alpha / 1.25`; update the same reference to `beta / -2.50`.
   Each operation has a same-predecessor read/no-op control and a reopened
   observer clone. Exact decimal strings are emitted only after numeric equality.
5. Export v1 and v2 CF on disposable producers. The producer imports/applies v2;
   the measured database is not changed early.
6. Load v2 CF into the measured branch. Verify designer v2 by a redump on a clone,
   while a fresh runtime session still reports applied v1 and the updated row.
   The matched control reloads v1 from the same updated predecessor.
7. Apply configuration separately. Freeze before any auxiliary operation, then
   verify runtime v2 and preserved reference/data. Its physical before/after
   comparison is explicitly **observational, with control=null**. No documented
   exit-only Designer batch command has been established, so this prototype
   does not fabricate an open/close control or substitute an export/check for it.
8. Dump DT from a clone of the frozen applied state. Physically delete the row in
   the original branch with a matched no-op control. A deletion mark is not enough:
   both the full catalog count and saved-reference query must be empty.
9. Restore DT into a distinct fresh database. Never run UpdateDBCfg after restore.
   Freeze first; verify v2 metadata, updated values, preserved reference, exact
   roles/users and continued absence of the row in the original deleted branch.
10. Stop/reap owned processes, remove raw files, remove the container, and verify
    private host staging removal before marking evidence accepted.

The finite report has 13 ordered stage records, 11 ordered snapshots and five
comparisons: four matched controls (create/update/load/delete), one observational
apply pair. All accepted states are checked again by the host against the exact
expected lifecycle. Failed runs stop dependent execution, retain only validated
partial observations and expose no ready CF/DT artifact summaries.

Version 2 retains this exact semantic lifecycle. Each successful frozen DB
snapshot additionally contains a finite `physical.header` object with
`status=header_layout_match`, a supported storage-format version, page size and
page count. Only exact formats `8.2.14.0` (4096-byte pages) and `8.3.8.0`
(4096/8192/16384/32768/65536-byte pages) are recognized. These are not the
installed platform version. Page count must be at least three and agree exactly
with physical length. A match is not proof of database validity or integrity.
Unknown versions, invalid layouts and policy failures stop the owning existing
stage with `invalid_header`; rejected header bytes never leave the container.

The shared standard-library decoder source `yadinassi/storage/filedb.py` is
included in the exact provenance manifest and staged as standalone `filedb.py`.
It does not import the yadinassi package, Interpreter or native runtime. Prefixes
are captured during both existing destination digest passes, at most 24 bytes
each, from the same already anchored no-follow descriptor. Both hashes and
prefixes must match and all existing file/ancestor checks still apply. There is
no new payload open, additional native command, or path-based inspection race.

Historically, header-only reports used `schema=2`, `lane=native-file-db-oracle-v2`. BSL markers,
completion markers, control data and invocation retain their independent schema
1. CF/DT summaries retain the exact four-field opaque shape with `header=unknown`.
All summaries retain `page_analysis=unsupported`; comparison windows remain
64-KiB byte windows, not storage pages. Report/file/live-byte/time caps and
cleanup acceptance are unchanged. Historical v1 reports must be audited with
their matching source revision, not silently accepted as v2 header evidence.

## Version 4 filtered physical-name comparison

The current host accepts only `schema=4`,
`lane=native-file-db-catalog-compare-v4`. Its strict validator retains every v2
lifecycle check, requires the exact current staged-source inventory, and rejects
historical v2/v3 transports rather than converting them.

The baseline `audit_contract` operation still uses Setup's existing identity and
nonprivileged module. It makes exactly one one-argument filtered
`ПолучитьСтруктуруХраненияБазыДанных(Отбор)` call for our own catalog. No native
invocation, schema/data mutation, privilege, user, UI step, external processor,
second Boolean or unfiltered fallback is added. The requisite column names were
measured by schema-3 run 40116987010. After checking declared/runtime types, the
projection reads only `ИмяТаблицыХранения`, nested `Поля`, and each field's
`ИмяПоляХранения`. It exports no metadata/logical names, tablespaces, indexes,
type values, row contents, or arbitrary scalar cells.

The native projection and independent reader projection each contain only the
fixed target and complete `{name, fields:[...]}` entries. Names are used exactly,
case-sensitively, with no guessed physical names, prefix stripping or type-code
mapping. Duplicate names are rejected before set/dictionary conversion. Native
tables must each match exactly one parsed table and all its parsed field names;
extra unrelated catalog tables stay private in a successful comparison. The
strictly bounded synthetic-only failure diagnostic below is a separate exception
for table names, never descriptor bodies or field/row data. Ordering is
canonicalized only for comparison. Unsupported naming conventions fail honestly, never by accepting a
partial match or applying an undocumented normalization.

The writable auditor clone's pre-launch digest must equal the frozen baseline.
Its fresh nonce/token are bound to that origin before the native launch. After
completion and process-census quiescence, the existing hardened freezer creates
a private read-only `auditor_frozen` postimage. The reader is staged standalone
as source-pinned `filedb_catalog.py`, without importing the Interpreter/package.
A hardened helper opens the frozen file once and uses that descriptor for
SHA-256 before, every positioned reader access, and SHA-256 after. Both digests
must equal the verified freeze summary; source/inode/mode/inventory/ancestor and
final process-census checks apply even on reader failure. Only after a complete
independent parse are native names used to select owned tables for comparison.
Both private clones are removed before the capture can be accepted.

The capture explicitly distinguishes baseline origin from the audited clone's
closed post-session image. It does not assert byte identity with baseline or the
file while native code was executing. Source-manifest and reader-source hashes,
operation nonce/token, actual platform version, origin/postimage sizes/digests,
exact storage version 8.3.8.0 and 8192-byte pages bind the comparison.

Per projection: at most four tables, 32 fields per table/64 total, 64 allowed BMP
units per name, 512 name units total, and 4096 encoded bytes. Empty/duplicate
names, incomplete enumeration, unexpected types and exhaustion fail closed,
without truncation. Both projections replace the historical shape payload; the
entire capture has its own 12288-byte ceiling. The unchanged full report ceiling
is 32768 bytes. The executable whole-envelope proof includes all 20 staged
source paths/hashes, maximal lifecycle snapshots/comparisons/opaque summaries,
longest finite enums and diagnostic fields, both projections and postimage
bindings, cleanup and final newline. The exact upper bound is 29821 bytes,
leaving 2947 bytes below the unchanged ceiling. Changing source inventory or
outer widths requires a new complete proof, not only a sub-payload check.

An accepted report requires the narrow match verdict and every original
lifecycle/cleanup gate. Failed comparisons ordinarily retain validated finite
category/code pairs: unsupported layout, conservative sharing policy, structural
rejection, resource exhaustion, source I/O/change, or name mismatch. Arbitrary
`CatalogError.code` values and exception text are never exported. A later
lifecycle/cleanup failure removes both projections and discards the successful
verdict. `not_run`, `failed`, and `discarded` do not mean physical-reader success.
All reports retain broad `native_compatibility=not_claimed`.

Tests cover actual current BSL projection under a controlled interpreter,
actual unchanged reader execution on a synthetic frozen descriptor, binding and
mutation failures, complete name matching, cleanup and report limits. These are
local mechanics, not native compilation or native physical compatibility. The
approved comparison design is in [the focused design note](file-db-native-catalog-comparison-design.md).

### Complete names-only diagnostic for a rejected synthetic comparison

Native run 40122436147 on commit
`85bc9328e2368ca1fd9a8141c8657a109cb71fa6` reached the completed reader and
postimage check, then failed baseline with `name_mismatch/missing_table`.
Its finite failure report contains no names and cannot establish the actual
naming or mapping cause. It is not native comparison acceptance.

A separate exact failure-capture variant (`storage_contract.schema=2`) may retain
a complete names-only observation for this specific rejection. The report stays
schema 4, status failed, reader failed and native compatibility not claimed.
The capture binds the same source manifest, reader source, operation nonce/token,
platform version, baseline auditor origin and closed frozen postimage as the
comparison. This is restricted to the harness's own synthetic disposable DB,
not an external or production database.

The diagnostic contains the complete selected native table-name list (1..4) and
complete parsed table-name inventory (0..64), sorted without silently removing
parser duplicates. Counts must equal list lengths. Every name must match
`[A-Za-z_][A-Za-z0-9_]{0,63}` and both lists together may contain at most 2048
ASCII characters. All names are observed literally. There is no case conversion,
prefix stripping, candidate selection, relation classifier, field-name export,
row value, raw descriptor, index byte, physical offset or interpretation of an
unmatched name. A limit or unsupported identifier produces a finite failure
without any partial name inventory. The existing capture/report caps still apply.

The diagnostic is allowed only after the complete independent parse and exact
same-descriptor postimage checks. Required native/raw cleanup must pass before
container output; all four cleanup checks must pass before final host output.
Any cleanup failure strips the names and binding to a bare finite failure.
The strict missing-table predicate and cross-field bindings are revalidated,
so a syntactically valid inventory cannot turn failure into acceptance. The
producer checks the actual launch token and freeze/read digest equality; an
offline validator cannot independently authenticate a sole token or postimage
digest merely from valid syntax. Their authenticity also relies on pinned
producer control flow and archived artifact digest/provenance evidence. These names
can reveal spelling differences; their absence cannot prove incorrect root
mapping, and they never authorize normalization or parser changes.

## Historical version 3 bounded storage-shape contract

The historical version-3 host accepted only `schema=3`,
`lane=native-file-db-shape-contract-v3`. Its strict validator reuses every v2
lifecycle check without accepting or converting a historical v2 transport.
Successful reports additionally require `storage_contract.status=shape_captured`.
`accepted=true` means lifecycle, shape-capture transport and cleanup passed; it
never means physical catalog parsing or native runtime compatibility is verified.

Only the existing baseline auditor clone uses `audit_contract`. The restored
clone still uses `audit`. No launch, native role, privilege, configuration object,
CLI option or control field is added. Setup identity is verified in the existing
nonprivileged server module before exactly one call:
`ПолучитьСтруктуруХраненияБазыДанных(Отбор)`, where the one-element Array contains
only `Справочник.NativeOracleItems`. The officially documented first argument is
[the filtered metadata-object selection](https://v8.1c.ru/obuchenie-programmistov/primery-razrabotki/sistemnye_protsedury_i_funktsii/kak_prosmotret_strukturu_tablits_informatsionnoy_bazy.htm).
There is no second Boolean, unfiltered fallback, external processor or retry.

The shape contains only column names, declared type-name lists and observed
nested ValueTable column signatures. Columns are discovered before accessing
nested cells; there are no assumed `Fields`/`Indexes` or physical-name fields.
Parent/column indices describe the signature relationship, not row values.
Scalar cells, metadata values, composite values, references, row counts and
exception text are not copied or rendered. Only declared Type objects may be
converted to strings. `nesting=observed_value_tables_only` explicitly makes no
claim that zero rows or untraversed composite cells prove empty nesting.

Counts are checked before loops/allocation: 16 table occurrences including
repeats, depth 3 below the root, 32 columns per table and 64 globally, 8 declared
types per column and 128 globally, 64 BMP units per name/type string and 768
units globally, 256 inspected rows and 4096 inspected cells globally. Repeated
objects and cycles consume these same budgets. Control characters, surrogates,
non-BMP strings, duplicate names/types and invalid parent references fail closed.
No output is truncated. A native budget failure carries only the fixed
`contract_limit` phase and becomes `artifact_limit`; other failures retain the
existing finite diagnostic policy. No cap is raised.

Both the fresh completion and strict result marker must validate before capture.
The capture binds the invocation nonce, exact operation token (a generated
correlation token, not a credential), canonical SHA-256 of the exact 18-source
manifest, frozen baseline digest and actual platform version. The report retains
the full individual source hashes, fixed image/platform/locale/timezone and
all existing cleanup gates. Failed lifecycle or cleanup strips the entire shape
capture. Neither partial result publication nor a valid result without completed
shutdown is sufficient. The host checks cleanup again before final acceptance.

The compact ASCII shape has an independent 8192-byte cap. A conservative
structural upper bound is 7350 bytes: all 16 table containers, 64 columns,
128 type entries with maximized array separators, plus 768 BMP units escaped at
six bytes each. The complete report proof does not stop at this sub-budget.
The executable test constructs an intentionally overlarge envelope containing
the actual 18 source paths and all hashes, all 13 stage/check containers,
11 maximal-header snapshots, all three opaque artifacts, all five comparisons
with maximum sample arrays and over-wide counters, the longest finite failure
and context enums, maximal basename diagnostic, full capture binding, cleanup,
and the full 8192-byte shape allowance. Mutually exclusive failure/success fields
are deliberately combined for an upper bound. Including the final newline,
the result is 25875 bytes, strictly below the unchanged 32768-byte transport
ceiling. Exact source keys and fixed provenance values are enforced by v3;
source/protocol changes must update and re-prove this executable bound.

Focused tests also run the exact BSL shape helpers under the project's controlled
Python interpreter: discovered nested tables, private scalar exclusion, zero-row
uncertainty, cycles, repeated aliases and row/text exhaustion. These are synthetic
source tests only. They do not establish native compilation, native API output,
physical table names or semantic reader agreement. Version 4 implements the separately scoped physical-name comparison above;
historical shape evidence alone never establishes that comparison.

Setup alone uses the privileged SessionModule and never performs catalog CRUD.
The ordinary dispatcher is a non-privileged server common module. CRUD does not
receive Administration, DataAdministration, FullAccess, interactive external
processor permissions or hidden extra roles. User authentication and dangerous-
action protection defaults are not assigned or relaxed. A separate named setup
user audit checks the global two-user inventory, avoiding permission widening
just to make that inventory available to CRUD. See the pinned original XML shape
and rights references in `scripts/native_1c_db_oracle/metadata/SOURCES.md`.

## Isolation, consistency and budgets

The exact approved image digest is
`ghcr.io/atridis/onec-ubuntu22@sha256:54e709c7f8eae8c92c5550a0378cef8b97236cc876f6c09591087f6abe9e7728`.
Isolation retains no network, UID/GID 1000, read-only root/inputs, no writable
host mount, no image logging, private IPC, dropped capabilities, no-new-privileges,
2 CPUs/2 GiB memory, 256 PIDs, 1024 FDs and the existing 1 GiB /tmp tmpfs. No
packages or third-party code are installed. A private authenticated display and
private session bus are owned by the controller; no host socket is attached.

Native commands run serially. Process-group wait plus PID/start-time census
must prove no native worker survives **before the first database payload read**,
including initial source hashing, and before/after copying. Controller summary
and comparison entry points are also census-gated. A completed marker, zero
DumpResult, stable mtime, sleep, matching hash or sidecar presence is insufficient.
Only the exact regular, single-link `1Cv8.1CD` payload is read, hashed and copied
from the source database directory; its identity/size/mtime/ctime and two source
digests must agree, and destination bytes are read back and hashed.

For this fixed synthetic configuration only, every other owned (UID/GID 1000),
single-link regular root file is a private **metadata-only** ancillary entry,
regardless of its basename. Owned root ancillary directories of any name use
the same bounded metadata-only walk formerly limited to `1Cv8Log`. All ancillary
entries together share the existing 16 MiB, 64-file, 128-entry and depth-2 limits;
zero-byte files count too. No ancillary payload is read, hashed, copied or
exported. Descriptor-relative no-follow/nonblocking opens verify type, identity,
ownership and stable metadata against anchored entries, then repeated inventories
must match across the copy. Links, special files,
wrong ownership, changing metadata and exhausted limits fail closed. This is
not a wildcard path input or a user-database backup contract.

This deliberately **replaces**, rather than strengthens or subsumes, the old
log-content-hash detector. An ancillary content change hidden behind identical
observed metadata is not detected; ancillary bytes are outside the snapshot
contract. Independent process census and the fixed synthetic workload are
therefore essential. No sidecar name or its presence/absence is a liveness test.
Frozen snapshots and clone sources/destinations remain strictly `1Cv8.1CD`-only.
The native semantic checks on disposable clones must prove the required catalog,
metadata, reference and user/role state before a snapshot is accepted. No claim
is made to preserve unrelated logs, session history, or arbitrary configuration
sidecar dependencies. Frozen files/directories remain read-only; native sessions
use writable clones. Existing destinations are never silently overwritten.

Clone-local byte accounting walks only the private artifact root, just as the
freeze helper accounts within that root. It must not rescan runtime HOME with
the helper's stricter database/artifact-only scanner: HOME may contain the
separately admitted pinned socket nodes. The outer controller still reserves
the complete clone size against **all private /tmp bytes before allocation** and
checks that same global budget afterward. No socket permission or allocation
limit is changed. Run [40098023212](https://github.com/Atridis/yadinassi/actions/runs/40098023212)
localized `invalid_input` to baseline observation after freeze returned; a
synthetic fixture reproduces the scanner-scope inconsistency, but does not by
itself establish the native failing suboperation.

Limits are independent of, and do not raise, the existing lane's limits:

- 64 MiB per raw file, 512 MiB cumulative regular files across the private /tmp,
  including native HOME, TMPDIR, metadata, caches and evidence. Only the two
  explicit X11/session-bus socket paths and the narrowly bounded owned HOME
  sockets described below are admitted as special entries.
- 1 MiB per native log, 16 MiB total native logs.
- 32 KiB complete public report and container transport, no binary payloads.
- 120 seconds maximum per native command, one 2340-second work deadline, and
  a 2400-second host container deadline including cleanup reserve.

The initial plan has about 49 native launches after omission of the unsupported
apply no-op and its observer sessions. A roughly 30-second allocation per launch
leaves time for setup, bounded streaming copies and cleanup within the existing
40-minute container ceiling. This is a budgeting assumption, not measured native
latency or a guarantee that every command can consume its individual maximum.
The total deadline always wins; exhaustion fails closed, never increases caps.
The 50-minute CI job includes registry setup/pull and teardown outside that run.

## What leaves the container

Only strict JSON containing fixed stage/state enums, booleans, exact expected
logical tokens, bounded numeric counters, hashes and sizes, plus the narrowly
bounded own-catalog physical table/field names described above. The report binds a
fresh 32-hex nonce, commit/tree, source hashes, pinned image, linux/amd64, fixed
ru_RU.UTF-8/Etc/UTC and measured SystemInfo.AppVersion `8.3.27.1508`.

No 1CD/CF/DT file, native log, raw error, XML/redump, UUID/reference, path,
credential, binary prefix, base64, unrestricted native string or page-digest map is
transported. The only additional version-4 native strings are the allowlisted storage-table
and storage-field names for the selected synthetic catalog; raw descriptors and
unrelated catalog names remain private. The workflow uploads exactly `native-db-oracle/report.json` after
strict validation and a descriptor-relative no-follow exclusive write on the
POSIX CI host. `report_ready=true` means that safe finite diagnostic report
exists, including a rejected run; it does not mean native success. Only
`accepted=true` in version 4 means all defined lifecycle, exact filtered
physical-name comparison, transport, provenance and cleanup gates passed, not
general native compatibility or row/type/index/write correctness. A failed cleanup may be diagnosed in this finite report but cannot
produce accepted evidence.

Seed failures may use only the fixed `seed_<operation>_<category>` enum, with
operations `create`, `dump_empty`, `import`, `apply`, `redump`, and `bootstrap`
and the existing finite native-failure categories listed in `protocol.py`.
The operation is recorded immediately before its launch attempt and cleared at
scope/stage transitions. Pre-launch failures and metadata preparation between
commands retain the generic category. `process_failed` proves a nonzero native
exit, not its numeric exit value or cause. Launch context is not proof of command
success. These diagnostics are accepted only for a failed `seed_v1` stage; no
new keys, raw logs, exception strings, native paths, or exit text are emitted.
A primary failure remains visible if cleanup also fails; separate cleanup
checks/stage still fail, and acceptance remains false. Later stages cannot
inherit a seed-operation label.

Bootstrap-only inventory failures additionally use a fixed
`seed_bootstrap_inventory_<phase>_<region>_<reason>` enum. The source-bound
phase is `poll` (a budget check following an alive-child poll) or `post_exit`
(the final budget check after zero native exit and quiescence). A poll rejection
is a monitor failure, not proof of native nonzero exit or that the child remained
alive until rejection; existing kill/reap and cleanup still apply. Regions are
only `home`, `tmp`, `runtime`, and `experiment`, selected from fixed controlled
prefixes. Reasons distinguish unexpected socket, symlink, hardlink, other
non-single link count, other special file, rejected ENOENT/ESTALE race,
EACCES/EPERM access failure, and other I/O error. No path, filename, raw errno,
exception, file content or log is reported. Already tolerated entry-disappearance
races remain tolerated. The classification itself changes no socket whitelist,
permissions, filesystem predicate, allocation limit, or quiescence requirement.
The separately reviewed HOME policy below is the only new typed exception.
Pre-launch failures and every other operation retain existing categories.

The inventory additionally permits at most **four** filesystem socket nodes
strictly below the preflight-created private HOME, only when UID and GID are both
1000 and link count is exactly one. Four is a conservative local fail-closed
ceiling, not a measured native requirement. The controller pins the parent and
HOME device/inode/ownership before native processes, verifies the same anchored
no-follow directory entries before and after every inventory, and revalidates
post-recursion ancestry on every path that used this new exception. HOME itself,
lookalike paths, replaced or renamed ancestry, unowned sockets, and other regions
are not covered. The existing two service socket names, all other special/link
rejections, regular-file accounting, entry/depth limits and process/snapshot
checks are unchanged. Neither socket names nor content are opened, connected,
copied, hashed or exported. A stale socket may remain after exit, but its presence
or absence never proves quiescence. HOME is never a database snapshot source.
Run [40092430401](https://github.com/Atridis/yadinassi/actions/runs/40092430401)
proved only a polling rejection of an unexpected HOME socket, not its name,
purpose, ownership or lifecycle. This policy checks ownership structurally;
it is not a claim that native bootstrap or the full oracle now succeeds.

Earlier exact-name compatibility steps admitted four documented zero-byte CFL
names ([release notes](https://dl05.1c.ru/content/Platform/8_3_4_365/1cv8upd.htm),
[CFL glossary](https://its.1c.ru/db/content/v8devgloss/src/term_000000179.htm)),
then the measured `1Cv8snc.1CL.cfl` from
[run 40096271107](https://github.com/Atridis/yadinassi/actions/runs/40096271107).
[Run 40097060683](https://github.com/Atridis/yadinassi/actions/runs/40097060683)
subsequently rejected the fixed session-history name `1Cv8snc.1CD` as an owned,
single-link, nonzero regular file. Both runs completed seed/version checks but
accepted no baseline or CRUD observation. The structural metadata-only contract
above replaces that evolving admission whitelist for this synthetic lane;
known-name classes remain diagnostic labels, not permission rules. No lifecycle
is inferred from a suffix, and fresh native clone verification remains required.

Baseline `invalid_input` failures have fixed `freeze`, `observe`, or `audit`
operation labels. Rejected root database entries additionally report only a
fixed class (database, one of the five CFL classes, session history, event log,
or other) and shape (owned/unowned zero/nonzero regular, symlink, hardlink,
non-single link count, directory, special, or invalid size). No actual names,
paths, numeric owners, file sizes, content or exception text are emitted by the
finite enum; the separately bounded failure-only basename field below is the
only name exception.
The exact finite vocabulary is in `protocol.py`; labels are scoped to a single
baseline call, never retained across stages, and accepted only for failed
baseline reports. Freeze/observe failures must have no completed snapshot;
audit failures require the completed baseline snapshot. Other error categories,
success schema, caps and independent cleanup remain unchanged.
Run [40093649254](https://github.com/Atridis/yadinassi/actions/runs/40093649254)
verified bootstrap, two users, metadata reimport and platform `8.3.27.1508`, then
failed with baseline `invalid_input`. Its output did not identify the rejected
entry or distinguish freeze from observation. Synthetic fixtures prove the old
policy rejects documented CFL files, not that CFL caused that native failure.

One failure-only optional `rejected_basename` diagnostic may identify an
otherwise rejected zero-byte, single-link regular root entry owned by UID/GID
1000. It originates only from the first source inventory of the original
synthetic `seed` database during baseline freeze, never a clone, destination,
later inventory, user database, file contents or full path. Its entire value
must match ASCII `1Cv8[A-Za-z0-9_.-]{0,48}` (4–52 characters). Names containing
separators, Unicode, whitespace/control characters, or any other prefix remain
unreported. The three documented base names `1Cv8.1CL`, `1Cv8tmp.1CD`, and
`1Cv8tmp.1CL` also have fixed diagnostic classes; these labels do not grant
admission independently of the structural guards above.
The field never changes admission. Under the structural policy an owned regular
zero-byte root sidecar normally needs no rejection diagnostic; accepted ancillary
names are never inventoried in public output.

The optional field is invalid on successful reports, other stages/operations,
other shapes, mismatched name classes, unmeasured versions, or mismatched
nonce/source provenance. Before host teardown it is only a private candidate
in captured stdout and requires successful native cleanup. The host discards it
on any later container/private-staging cleanup or provenance failure; the final
public report requires all four cleanup checks true. Existing primary failure
categories remain visible if cleanup fails, without the basename. Success keys,
raw-data restrictions, byte/report limits, permissions and admission policy are
unchanged. This narrowly bounded diagnostic is not a general filename inventory.

The absent logical fields in the fixed BSL markers use `Неопределено`, which
[automatic JSON serialization](https://v8.1c.ru/platforma/json/) maps to JSON
`null`; automatic reading maps that representation back to `Неопределено`.
These are present properties with absent values, not omitted properties and not
semantic BSL `Null` observations. The bootstrap writer, server result defaults,
empty-state values and create-state absence check use the same representation.
The Python wire contract still requires every exact key and the same `None`
values; populated values and reference booleans are unchanged. This follows the
[previous reviewed transport correction](native-client-async-measurement.md#error-descriptor-json-transport-correction),
not a change to runtime Null behavior or native evidence. Run
[40090298567](https://github.com/Atridis/yadinassi/actions/runs/40090298567)
localized a nonzero exit to bootstrap, but did not identify its cause. The
transport correction is not a proven repair until fresh native evidence passes.

Historical version 1 classified all binary headers as unknown. Version 2 checks
only the bounded frozen DB header; CF/DT headers remain unknown and page analysis
remains unsupported. Differences are streamed as **64 KiB byte windows, not pages**.
Changed/added/removed bytes, size deltas and bounded sample indices are validated.
Control/treatment overlap is an observation, not causal subtraction or proof of
row-page locations. Deletion need not shrink a database; a restored DB need not
match its source bytes. CF and DT are distinct artifact kinds and are not assumed
to share a 1CD layout. This lane makes no format-parser completeness claim.

## Capability gates and offline validation

Official 8.3.27 documents support the intended commercial-platform batch command
families: [configuration import/export](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.27_Administrator_Guide/Appendix_7._Startup_command-line_options_of_1C_Enterprise/7.4._Running_Designer_in_batch_mode/7.4.4._Configurations_and_extensions/?language=tr),
[DumpIB/RestoreIB](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.27_Administrator_Guide/Appendix_7._Startup_command-line_options_of_1C_Enterprise/7.4._Running_Designer_in_batch_mode/7.4.2._Dumping_restoring_infobase/?language=es),
and [DumpResult](https://kb.1ci.com/1C_Enterprise_Platform/Guides/Administrator_Guides/1C_Enterprise_8.3.27_Administrator_Guide/Appendix_7._Startup_command-line_options_of_1C_Enterprise/7.4._Running_Designer_in_batch_mode/7.4.17._Other_parameters/?language=tr).
They do not establish that this exact training binary accepts the original XML,
all Russian API spellings, narrow rights/default authentication, or every switch.
Those remain native compilation/runtime gates until an accepted run. An error
is not evidence of its cause; do not automatically broaden rights, alter defaults,
add speculative flags, or treat a successful local parse as native proof.

Run offline tests from the repository root:

```sh
python3 -m unittest discover -s tests -p 'test_native_1c_db_oracle_*.py'
python3 -m unittest discover -s tests
```

Offline fixtures mock the platform boundary or synthesize byte strings. They
exercise lifecycle ordering, failed commands/markers, stale evidence, exact
report schemas, non-finite/duplicate JSON, source mutations, live-writer gates,
symlink/hard-link/side-file rejection, budgets, separate role/metadata definitions,
cleanup rejection, reviewed-push policy and unchanged legacy gates. Native-only
POSIX filesystem checks are skipped on unsupported hosts; portable validators
and orchestration tests still run. None of these tests executes 1C or licenses a
claim of native success.

### Controlled failure completion and bounded command context

The managed startup handler now catches controlled dispatch/transport failures and
attempts normal shutdown once. The server catches on the server side and returns
only fixed status/operation/subphase values; it never reads exception descriptions.
This does not depend on scalar by-reference copyout across a failing server call.
Existing transaction rollback and all role, isolation, timeout, and byte limits are
unchanged. The prior uncaught call could skip shutdown; that source weakness does
not establish the cause of the measured create-stage timeout.

Each ENTERPRISE session must now produce a separate private `completion.json`,
exactly bound to schema, source nonce, fresh launch token, operation, status and
fixed phase. It is written to a fixed pending filename, closed, checked again for
an existing destination, then moved within the same directory. This is a
close-then-move publication sequence, not a claim about native filesystem atomicity
or a general no-replace primitive. The host accepts semantic success only with an
`ok`/`complete` completion **and** the strict success result marker. The production version-4 `audit_contract` result requires its bounded
`storage_names` projection. The marker decoder selects version 4 explicitly and
requires its exact mutually exclusive key set; historical shape fixtures use
the separately selected version-3 shape marker, not an automatic fallback.
An error completion never becomes success even when `result.json` exists. Missing,
stale, malformed or incomplete completion fails closed. Private marker files,
arbitrary exception text and native paths are not exported. Versions 3/4 export only the
fresh `audit_contract` correlation token inside their explicitly bound capture;
other launch tokens remain private.

A failed report may include one finite `failure_context` object: command operation,
supervisor site, optional fixed BSL phase, and optional fixed inventory region and
reason. Context is lexically attached to the failing operation and bound to its
stage; it is never a sticky previous-command label. Inventory classifications are
preserved outside seed as well. The public field requires all four cleanup flags;
late host teardown/provenance failure strips it. The historical v2 context-only change did not alter successful report keys;
v3 has historical shape fields and v4 has the separately versioned comparison
fields described above. A timeout command/site identifies the supervised command, not
its internal cause or whether a transaction committed. A caught BSL phase records
the last source-assigned boundary, not native error text or proof of rollback.

The new local exception/rollback/publication tests execute rendered synthetic BSL
with controlled stubs. They are offline harness tests, not native platform evidence.

### Private reference JSON transport

The private reference helper now uses the already exercised JSON read/write helpers
instead of TextDocument operations. Its exact two-field object contains the source
nonce and a canonical UUID string; neither value is added to public output. The
nonce must match, the UUID must be a String of length 36, and parsing it as a UUID
then converting back to String must reproduce it exactly before the unchanged
catalog GetRef/query checks. Existing-file rejection preserves one-write evidence.
The fixed `reference_uuid` phase separates UUID conversion from `reference_write`.

Only this private helper's pre-read file cap changes from 64 to 128 bytes to fit the
nonce-bound object. Its compact ASCII representation is 95 bytes; UTF-8 BOM and a
four-space/CRLF rendering total 114 bytes. The cap still applies before the generic
JSON reader is called, independently of that reader's existing 4096-byte limit.
All aggregate, raw-database, timeout and public-report limits remain unchanged.

The measured prior run reached the reference-persistence group after write and
commit returned, but did not establish a reopened row. This substitution removes
an unexercised auxiliary transport dependency; it does not diagnose a TextDocument
bug or establish native CRUD success. Native execution of the exact revised source
and the unchanged reopen/reference assertions remain required.
Exactness here means the parsed object's shape and values. The existing automatic
JSON reader is unchanged; this lane does not newly claim native rejection of raw
duplicate keys or trailing JSON tokens. The input remains its own write-once private
marker, not a caller-supplied document.

### Snapshot-boundary failure localization

Finite failure context also covers snapshot freeze, clone and removal throughout
the fixed lifecycle. A database-entry rejection may carry only the existing fixed
entry-class/shape pair, never a basename, path or contents. Live-source ancillary
inventory, strict frozen/clone inventory, file ownership/link checks, census,
copy verification, and every resource bound are unchanged.

Auxiliary-clone cleanup is attempted after both success and failure. If the main
operation already failed, a removal failure no longer replaces its primary error
or context; the enclosing mandatory cleanup and final cleanup gates still run.
If the operation succeeded but removal fails, the operation remains a failure.
This rule applies to observation, audit, configuration producers and DT dumping,
not just restoration. Optional context is still removed when final cleanup cannot
be verified, and successful report bytes remain unchanged.

The prior run proved the complete lifecycle through physical deletion, but failed
before a restored snapshot was appended. Source-bound synthetic fault injection
localized a diagnostic gap after the restore command wrapper, including the
possibility that auxiliary removal masked an earlier error. It did not establish
a native restore defect, an ancillary-file cause, or grounds to widen admission.


### Bounded ancillary directories after restore

The source-only ancillary policy now permits directory trees of any basename,
subject to the **same shared** 16 MiB, 64-file, 128-entry and depth-2 bounds as the
previous log tree. Every directory and regular file must be owned by UID/GID 1000;
regular files must be single-link. Descriptor-anchored no-follow traversal,
ancestor/entry identity checks, stable pre/post inventories and native-process
census remain mandatory. Links and special nodes remain rejected. Exact
`1Cv8.1CD` takes precedence and remains the sole payload that is read, hashed or
copied. Ancillary content is never read, hashed, copied or exported; read-only
opens are used only for descriptor metadata verification. Frozen sources, clone
sources and every copy destination remain strictly database-only.

This deliberately removes the root-directory-name anomaly detector. It is not a
security superset and does not infer the name, ownership, purpose or safety of the
previously rejected native directory. Ownership and shape must now be verified
structurally before acceptance. Existing metadata-only limits do not detect
content changes that preserve every observed metadata field.

The contract applies only to the immutable synthetic one-catalog configuration,
which has no external storage dependencies and accepts no user database input.
A copy of `1Cv8.1CD` alone is not advertised as a general database backup. The
restored clone still must pass all reopened row/reference, metadata and user-role
checks before the oracle can succeed. This policy change is not native proof that
restoration succeeded; that remains an exact-source native execution gate.
