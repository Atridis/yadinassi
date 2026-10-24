# Synthetic native file-database oracle, version 1

Status: implementation and offline fixtures, **not yet native evidence**. This is
an independent opt-in experiment, not a 1CD/CF/DT parser, writer, or runtime DB
implementation. Existing six-scenario outputs, caps, goldens, bootstrap and CI
acceptance remain unchanged.

The original fixture contains one non-hierarchical catalog, NativeOracleItems:
Code `K1`, Payload String(32), Amount Number(9,2). The only v2 schema change is
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
   inventory audit run on disposable clones, never the frozen bytes.
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
must prove no native worker survives before every snapshot. A completed marker,
zero DumpResult, stable mtime, sleep or matching hash alone is insufficient.
Only a regular, single-link `1Cv8.1CD` is copied from a closed database directory.
The documented optional sibling `1Cv8Log` directory has a private stable inventory
limited to 16 MiB, 64 files, 128 entries and depth 2; its contents are never copied
or reported. Links, special files, changing inventories, and every other sibling
name (including unreviewed lockfiles) fail closed. Log presence or absence never
substitutes for process quiescence. Snapshot source identity/size/mtime/
ctime and two source digests must agree; destination bytes are read back and
hashed. Frozen files/directories are read-only. Observer/export/native reopening
uses writable clones. Source copies are never silently overwritten.

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
logical tokens, bounded numeric counters, hashes and sizes. The report binds a
fresh 32-hex nonce, commit/tree, source hashes, pinned image, linux/amd64, fixed
ru_RU.UTF-8/Etc/UTC and measured SystemInfo.AppVersion `8.3.27.1508`.

No 1CD/CF/DT file, native log, raw error, XML/redump, UUID/reference, path,
credential, binary prefix, base64, arbitrary native string or page-digest map is
transported. The workflow uploads exactly `native-db-oracle/report.json` after
strict validation and a descriptor-relative no-follow exclusive write on the
POSIX CI host. `report_ready=true` means that safe finite diagnostic report
exists, including a rejected run; it does not mean native success. Only
`accepted=true` means all native, semantic, transport, provenance and cleanup
gates passed. A failed cleanup may be diagnosed in this finite report but cannot
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

Native-source freeze inventory permits the four exact documented
`1Cv8.1CD.cfl`, `1Cv8tmp.1CD.cfl`, `1Cv8.1CL.cfl`, and `1Cv8tmp.1CL.cfl`
siblings. The [official release notes](https://dl05.1c.ru/content/Platform/8_3_4_365/1cv8upd.htm)
and [CFL glossary](https://its.1c.ru/db/content/v8devgloss/src/term_000000179.htm)
describe zero-size lock-coordination files that may persist after clients exit.
This lane requires regular zero-byte files, one link, UID and GID 1000, no-follow
opens and stable descriptor/anchored-entry identity, metadata and ownership at
repeated pre/post-copy inventories. It never reads their content, copies them to
snapshots/clones, or exports them. Exact membership originally bounded their count at four;
there is no wildcard, size allowance, or new filesystem permission. Frozen
sources remain strictly 1CD-only. Session history `1Cv8snc.1CD` and all other
unknown siblings remain rejected. Existing event-log limits are unchanged.
CFL presence or absence is not evidence of quiescence; independent process
census and stable database copying remain mandatory.

Run [40096271107](https://github.com/Atridis/yadinassi/actions/runs/40096271107)
subsequently measured one additional rejected basename, `1Cv8snc.1CL.cfl`,
from the first original seed-source inventory: regular, zero-byte, single-link,
UID/GID 1000, with all four cleanup checks verified. That **one exact name** is
now admitted under the identical metadata-only CFL guard, bringing the fixed
maximum to five. This is based on observed shape and confinement, not an inferred
lifecycle or guarantee from its suffix. Its contents remain unread, uncopied and
unexported. `1Cv8snc.1CD.cfl`, session-history database files and every other
unlisted name remain rejected. A fresh native run must still establish baseline
and CRUD behavior; the measured rejection did not establish either.

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
`1Cv8tmp.1CL` also have fixed rejection classes; this does not admit them.
All unknown entries still fail closed, including names eligible for diagnosis.

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

Version 1 deliberately classifies all binary headers as unknown and page analysis
as unsupported. Differences are streamed as **64 KiB byte windows, not pages**.
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
