# InformationRegister keyed read — NEW v2 measurement lane

Local source preparation on main `273d40ab0abb3fad2a4489ba2cefa100c189dfc8`.
This is a new reconstruction after an environment reset, not recovery of v1 bytes.
The corrected input preparation was composed with main `6c4da390` without
changing its production runtime. Native run `41353896285`, source `03e18b8c`
(tree `d7407d9d`, identical to feature `c0ee2060`), accepted both strict redumps
and captured all 32 blocks across eight contexts. The 16 client/server block
pairs agree; cleanup is complete. Original authenticated reports stay private.

The completed read-only runtime is described in [InformationRegister reads](information-register-readonly.md).
Its captured-byte replay is not actual database parity: a fresh final-source
frozen `.1CD` comparison and full/CI gates remain pending.

The closed `information-register-read-v2` selector reuses the existing reviewed
file-DB workflow/job, owner/exact-ref/source checks, image, credentials, process
confinement and cleanup. No new trigger, permission, user, role or user database.
The current default selector is intentional only on this candidate feature.

## One bounded functional batch

Two saved identities, reversed dimension/resource declaration orders; empty and
filled clones; client and server observations. Four independently bounded blocks
of 24 scalar observations run within each of eight observation sessions, plus
four setup sessions (12 sessions total, not 96 cold launches).

The independent nonperiodic register has Product (one fixed CatalogRef, indexed)
and Variant (Number9.0) dimensions; Price (Number9.2), Available (Boolean) and
ValidUntil (DateTime) resources; Note (String32) attribute. The disposable target
catalog has two generated rows. Three register records have unique full keys.
Setup uses explicit `Write(False)` only on this owned fixture; the existing CRUD
role gets only register Read/Update. Exact role comparisons prohibit extra grants.
The public target API is read-only full-key Get and one indexed Product Select.

An independent native Query supplies 24 setup/count/key/value witnesses. Observer
blocks never query or write. Register/catalog Metadata controls distinguish real
context unavailability from observer failure; no manager.Metadata assumption.
RGCount declarations remain unique per setup block at module scope. Unsupported
client globals/assignments are resolved dynamically inside each lexical observer.

## Identity, snapshots and raw evidence

Source XML and identities are frozen. Full redump tree/attribute/text equality
uses semantic USED QName bindings; no arbitrary native-default stripping. Only
UUID+Name+kind-matched generated register/catalog XML (at most64KiB each) may be
retained as diagnostic evidence. Such capture does not accept normalization.

Native acquisition closes before the snapshot is frozen. Raw CONFIG/PARAMS/table
observation and actual offline Interpreter use the same pinned postimage under
before/after digest and quiescence checks. Complete CONFIG evidence includes root,
root target, owned register/catalog and the per-run verified NativeOracleItems
baseline. DBNames preserves all roles of selected owned UUIDs; `_InfoRg<id>` is
only a measurement table-name hypothesis, not a production binding. Unknown or
ambiguous kinds/table absence retain finite unresolved evidence. No register
record UUID, row stride, order, key, null/free-slot or reference encoding is guessed.
Shared existing read/page/byte caps and cross-reader ownership checks remain.

Typed offline layout failures can retain already validated native wire only as a
FAILED report after final snapshot verification; integrity/I/O/OracleError still
propagate. No failed/unavailable observer can be marked matched parity. Every raw
capture stays source-bound; native success alone is not runtime acceptance.

Public future replay fixtures must contain only required owned CONFIG/rows,
programs, observations and provenance hashes. Installations/audits/session tokens
and nonces are excluded from construction; authenticated original reports stay
private. No proprietary primary archives are included in the published sources.

# !todo Periodic/recorder-driven registers, slices, composite dimension types,
# advanced filters/order, writable APIs and unmeasured free chains are deferred.

## DOM main composition

The current candidate combines the register family with main `fa089d70` (DOM).
The runtime inventory is 111 (106 plus five register modules), with unchanged caps.
The earlier actual register parity run `41356947535` remains evidence for its
original source; fresh actual file-DB parity and tiered CI are required for this union.
