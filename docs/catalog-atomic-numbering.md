# Atomic local catalog numbering and durable write outcomes

This is an explicitly host-authored local `decimal_v1` contract, not measured
native 1C automatic-numbering parity. The default XML importer still refuses
`Autonumbering=true`. An explicit local-policy opt-in now admits that flag only
within the otherwise supported closed XML profile. It does not execute configured
modules, install forms, or bypass any other activation issues.

## Closed metadata and storage profile

`CatalogSchema.numbering` defaults to `explicit`. Host-authored schemas may select
`decimal_v1` only with a String code width from 1 through 9. Numbered databases
are newly created owned SQLite v4 files, with durable per-catalog UUID counters.
Existing explicit-only schemas still create v2 or v3 files. Existing v1/v2/v3
schema serializations are preserved, and opening them never
adds counters or migrates their data. No v3-to-v4 migration is supplied.

The policy is deliberately precise: auto candidates start at 1, use ASCII decimal
zero-padding to the declared code width, and advance monotonically within the
transaction. Exact occupied codes are skipped, bounded by the admitted catalog
record limit. Manual explicit codes neither advance nor reset the counter; a
future automatic candidate skips an exactly matching existing manual code.
Exhaustion refuses with `code_exhausted`, never wraps, truncates or changes width.
Deletion marks retain their codes. This policy must not be described as every
native 1C numbering rule, including prefixes, manual numbering, concurrent
reservations, resets or reuse.

`CatalogDraft.auto_number=True` is an explicit create-only request, with an empty
submitted code and an enabled schema. False preserves explicit-code behavior;
numbered catalogs reject a blank explicit code. Updates cannot auto-allocate.
All numbering and owner/section insertion occur under the existing
`BEGIN IMMEDIATE` transaction and per-record savepoint. Any record failure rolls
back the counter with that record's data. Competing
backend connections serialize through SQLite or receive the existing bounded
busy refusal; no number is allocated on opening a form or making an edit.

## Write outcomes and uncertain commits

V4 advertises `catalog_write_outcomes`. After confirmed COMMIT,
`commit_outcomes()` returns ordered `CatalogWriteOutcome(revision, code)`
values; `commit()` retains its revision-only result. No successful outcome
is inferred from a subsequent read.

Automatic numbering applies only to a new object with an empty Code and a
schema that selects this profile. Runtime objects receive the allocated code
only after a confirmed commit. If the outcome is unknown, the submitted buffer
and its sections cannot be written again. Read the current record with a fresh
object. A confirmed rollback leaves the number available for a separate new
write. See [unknown commit outcomes](sqlite-commit-uncertainty.md).

## Boundaries and follow-up

No UI automatic-numbering control, general configuration activation, BeforeWrite
dispatch, schema-update workflow or native-numbering behavior claim is added.
Full demo XML admission still needs separate review of its complete modules and
forms; this option cannot replace unsupported source with a local profile.

The native follow-up must measure initial formatting, explicit/manual code
interaction, width exhaustion, failed writes/cancellation, assignment timing,
deleted records/marks and repeated or uncertain client calls within an authorized
bounded experiment. Local SQLite tests establish the specified local atomicity
and recovery contract, not those unmeasured native rules.

## Explicit XML import opt-in

Use `import_configuration(files, numbering_policy="decimal_v1")` or
`load_configuration_directory(directory, numbering_policy="decimal_v1")` to choose
this local contract deliberately. Only catalogs whose source says
`Autonumbering=true` select it, and their String code width must be 1–9.
Unflagged catalogs retain explicit codes. Hierarchy, owners, nonunique codes,
other series, executable modules, forms and unknown metadata retain their
existing refusals. In particular, exact rich Designer envelope witnesses that
pin `Autonumbering=false` are not widened: changing their flag still prevents
activation. The new active path covers the minimal closed XML envelope, not
arbitrary Designer dumps. Source files are retained byte-for-byte, and generated
numbering policy is persisted in the v4 schema. No existing database is migrated.

CLI example for an otherwise admitted source package:

```
python -m yadinassi --create-db app.sqlite --import-xml source --numbering-policy decimal_v1
python -m yadinassi --f app.sqlite -c 'O=Catalogs.Categories.CreateItem();O.Description="saved";O.Write();Message(O.Code);'
```

The option is creation-only and cannot be combined with execution or `--f`.
It does not activate the original full demo configuration or establish native
numbering parity. The full demo's unsupported form/module gates remain closed.
