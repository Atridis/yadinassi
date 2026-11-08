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
schema serializations and receipt digests are preserved, and opening them never
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
back the counter and that record's receipt bookkeeping with the data. Competing
backend connections serialize through SQLite or receive the existing bounded
busy refusal; no number is allocated on opening a form or making an edit.

## Write outcomes and uncertain commits

V4 advertises `catalog_write_outcomes`. `commit_outcomes()` returns immutable
`CatalogWriteOutcome(revision, code)` values after the confirmed commit and
connection cleanup. The existing `commit()` API retains its revision-only result
for host callers. Both use the same atomic transaction and durable receipt.

V4 receipts retain the code as well as the revision and bind the original
submitted request, including its `auto_number_v1`/`decimal_v1` marker, to the
recorded outcome in one versioned digest. The request is not silently replaced
with a generated-code draft. `resolve_write_outcome()` returns that exact
recorded result, including the original code if the record was later edited.
It does not derive a result from a new card read or allocate a replacement code.
For multi-write transactions, `resolve_write_outcomes()` verifies the complete
ordered tuple of `CatalogWriteRequest` intents and returns every original code;
see [batch receipt recovery](catalog-batch-receipts.md).
`resolve_write()` and `committed_operation()` retain revision-only views.

This is structural/integrity checking of owned storage, not cryptographic
protection against a same-user attacker rewriting a database and its hashes.

The runtime requests automatic numbering only for a new object whose Code is
empty and whose schema explicitly selects this profile. A backend without outcome
capability refuses that profile. Runtime buffers receive the code only after a
validated committed outcome. An uncertain COMMIT or cleanup freezes the original
request and nested section buffers; another Write resolves the receipt or retries
only a proven uncommitted intent. It never blindly creates a second record. A
failure before commit leaves the code unassigned and the edit buffer available.

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
