# Owned-fixture baseline metadata observation, version 1

This is a separate bounded observation lane, not logical field mapping, record
readback, native compilation evidence, or general 1CD compatibility. It replaces
the baseline names-only capture slot in this lane with one metadata/declaration
capture. The unchanged lifecycle still has 13 stages, 11 snapshots and five
comparisons. The Python language/runtime and physical catalog parser are unchanged.

## Explicit route, no default opt-in

The existing command, without an extra flag, retains the names-only report-v4
lane and its exact 20-entry staged-source inventory. The new module is not staged
or imported on that route. Its historical validators remain closed to the new
operation, marker payload, capture and report fields.

The additional explicit host flag is the only selection mechanism:

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --record-metadata-observation --output native-db-oracle/report.json
```

It selects invocation schema 2 with lane
`owned_record_metadata_observation_v1`, report schema 5, capture schema 6, and
exactly 21 staged source entries: the old 20 paths plus `record_observation.py`.
The host, read-only probe and private controller propagate this selection; no
process environment, database path, command argument inference or payload value
can silently opt in. Cross-lane invocations/inventories are rejected.

The dedicated reviewed-branch workflow explicitly adds this flag to its existing
host command. This selects the observation lane for that workflow only; the
no-flag CLI remains names-only v4. The reviewed branch, triggers, permissions,
pinned actions, artifact path and cleanup gates are unchanged. Before advancing
the reviewed branch, review the exact candidate and workflow command. This
selection does not establish a native result, logical mapping or record
acceptance. Publication remains gated on completion of PR104; local preparation
does not authorize native execution or publication.

Shared `host`, `inputs`, `probe`, `run`, server BSL and managed-client dispatch
sources do change. Their new hashes must appear in whichever lane is executed.
Preserved old behavior does not mean byte-identical old sources, and historical
native results cannot be relabeled as evidence for this revision. The old
`NativeИменаХранения` helper, historical protocol/comparison validators, metadata,
roles, SessionModule, CRUD values and operations remain unchanged.

## Native same-row projection

The new baseline operation `audit_record_metadata` runs as the existing Setup
identity on the existing disposable auditor clone. The unchanged singleton role,
nonprivileged execution, two-user inventory and fixture metadata checks apply.
It calls the filtered storage-structure API exactly once for
`Справочник.NativeOracleItems`, with explicit `Истина`. There is no default-mode,
unfiltered or retry fallback.

After required declared-column and actual-cell type checks, it admits exactly
one table and its complete 1..16 fields. It emits unchanged same-row root
`storage_name`, `logical_name`, `metadata_name` strings and each field's unchanged
`storage_name`, `logical_name`, `metadata_name`, `type_text` strings. Empty
nonstorage strings remain valid observations; missing/wrong-type cells reject.
No logical spelling, `_Fld` suffix, position, type text or stored value establishes
a mapping. `type_text` is uninterpreted vendor text.

Every cell is at most 64 printable BMP units, with 768 units cumulatively and a
6144-byte compact ASCII-JSON projection ceiling. The native and host validators
share frozen Unicode 15.0.0 printable BMP ranges: no controls, surrogates, format
characters, private/unassigned code points or Unicode-version-dependent widening.
Storage identifiers additionally satisfy `[A-Za-z_][A-Za-z0-9_]{0,63}`. The helper
reads no indexes, tablespaces, purpose, arbitrary cells or row data. Counts and
cumulative budgets are checked before additional allocation; no truncation.

## Independent complete declarations

Before the native launch, the writable clone's complete size/digest must equal
the frozen baseline. After the session closes and process census is quiescent,
the hardened freezer captures its private postimage. Both origin-clone and
postimage-overlap bytes are reserved within existing live-file limits.

The unchanged standalone catalog reader completes its independent parse before
native names are supplied for selection. It then selects exactly one physical
table by exact storage name and requires complete field-name bijection under the
unchanged fixture policy `exact_tables_ascii_fields_v1`: ASCII case keys only,
with raw duplicate and same-side collision rejection. Raw spellings remain intact.
The broader old projection validator's 512-unit budget is not reused to shrink
this lane's explicit 768-unit metadata/declaration observation budget.

The sole selected physical projection contains table name, original record-lock
token and **every** ordered field declaration: original name, type token,
nullability integer, length integer, precision integer and case token. Order is
not an offset claim. Text is limited to 768 units; names to 64 ASCII identifier
units; tokens to 0..8 ASCII letters/digits/underscore; integers to 0..65535;
complete projection to 4096 bytes. Empty tokens are uninterpreted observed
absence, not an inferred type/lock/case policy. Unsupported declarations reject.
No descriptor bytes/AST, Files references, indexes, unrelated table metadata,
row bytes, data-header or slot reads are exported or needed.

## Bound evidence and cleanup

The capture binds source manifest, independent reader hash, nonce/fresh token,
platform version, exact origin size/digest and closed postimage size/digest,
8.3.8.0 storage version and 8192-byte pages. Commit/tree, exact staged-source
hashes, image digest, locale and timezone are bound in the strict report.
The postimage is the reader target; byte identity with the origin is not assumed.

Successful bounded observation reports `metadata_projection_captured`, the
existing narrow field-name verdict, `mapping_validation=not_run`,
`layout_validation=declarations_only`, `record_validation=not_run`, and
`native_compatibility=not_claimed`. Unknown or empty logical cells cannot earn a
mapping verdict. Unsupported observations retain only finite reviewed error
category/code pairs, never exception strings, paths, command lines or logs.

All later lifecycle failures discard the metadata and physical projections and
the successful verdict. Publication requires all four existing cleanup gates:
owned native processes stopped/reaped, raw artifacts removed, container removed,
and private host staging removed. Both auditor and frozen postimage are removed
before their evidence is returned. Successful lifecycle alone does not bypass
host cleanup.

File/live/time caps remain 64 MiB per raw file, 512 MiB live, 120 seconds per native
command, 2340 seconds internal work and 2400 seconds host execution. Combined
capture cap is 12288 bytes; complete report including newline remains 32768.
The executable budget proof in `test_native_1c_db_oracle_record_budget.py` charges
all exact keys, 21 source paths/hashes, independently maximal lifecycle fields,
finite diagnostics, cleanup and newline. The complete native projection upper
bound is 5938 bytes; physical declaration upper bound is 2476 bytes. Reserving
the full independent 6144+4096 projection allowances gives a complete capture
bound of 11090 bytes. Charging the entire 12288-byte capture cap in the complete
report yields 30205 bytes including newline, leaving 2563 bytes below 32768.
The tighter derived-capture report bound is 29007 bytes. These are conservative
independent maxima, not a claim that all maxima form an admitted observation.
Old-lane 29949-byte arithmetic is not used as the new report proof.

## Evidence boundary and next steps

Controlled interpreter execution of the actual BSL helper, isolated staging,
synthetic physical descriptors, protocol mutations, negative controls, cleanup
failures and whole-envelope bounds establish local mechanics only. Fresh
reviewed source-bound native capture is still required before any mapping
profile is approved. Prior one-argument shape evidence proves column names and
types only, not explicit-True cell values or mappings.

Subsequent v1 row acceptance, separately reviewed, is empty/create/update only.
Existing physical deletion follows v2 widening and is not a v1 deletion branch.
Prospective experimental reader defaults (4096 slots, 4096-byte records, 16
fields) and an owned-oracle at-most-one-active-row admission condition are not
universal format rules. This observation reads no records and imports no
experimental row reader. No Tool1CD implementation is copied, translated or
introduced as a dependency.
