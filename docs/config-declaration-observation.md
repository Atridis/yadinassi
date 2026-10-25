# Experimental CONFIG declaration observation

This is a separately selected **observation-only** lane. It does not extract a
configuration file, decode row framing, identify a root entry, establish applied
configuration semantics, or add BSL `Metadata`/`Метаданные` managers. Synthetic
unit tests are not native evidence; this lane has no accepted native result yet.

## Selection and evidence boundaries

`--config-transport-observation` is mutually exclusive with every existing oracle
mode. It selects `owned_config_transport_observation_v1`, report schema 10,
capture schema 11 and invocation schema 7. Its exact 22-source inventory is the
record-observation inventory plus `config_observation.py`; it does not import or
stage the PARAMS policy, DBNames parser or extraction reader. Existing default,
PARAMS, DBNames and record lanes keep their schemas and source memberships.
The existing reviewed workflow explicitly selects this declaration lane with
`--config-transport-observation`, replacing its previous identity selector. Its
trigger, immutable checkout/actor admission, image, permissions and report-ready
gates are unchanged. This activation is not a native result: no CONFIG observation
has yet been accepted. The explicit DBNames identity mode remains available but
is not exercised by this workflow selection; standard native runtime checks do
not substitute for a dedicated CONFIG observation.

The observation uses the existing baseline auditor's frozen post-session image.
There are no extra 1C commands, users, permissions, lifecycle stages, clones or
snapshots. The 13 stages, 11 snapshots, five comparisons and four cleanup gates
remain mandatory. Source manifest, reader/policy hashes, nonce/token, platform,
origin and closed-postimage digest bindings are independently validated. Later
failure invalidates a successful capture; stale, missing or extra fields fail.

## Finite raw facts, not a storage profile

One `CatalogReader` selects exactly one ASCII-case-insensitive CONFIG table and
uses its identity-bound data/BLOB internal files with shared ownership/budgets.
CONFIGSAVE is not a fallback. Only the following finite facts can be projected:

- fixed CONFIG spelling;
- record-lock token (up to eight ASCII identifier characters);
- format discriminator: integer-zero/nonzero, string-zero/other, list or other;
- six or seven ordered system-container fields: FILENAME, CREATION, MODIFIED,
  ATTRIBUTES, DATASIZE, BINARYDATA and optional PARTNO; each retains bounded type
  and case tokens plus integer nullability, length and precision (0..65535);
- bounded logical data/BLOB lengths;
- class of logical data byte zero: zero, one, other or unavailable.

Unknown names/count/order or unbounded declaration values fail before selected
file access. The reader does not export arbitrary names, ASTs, rows, filenames,
UUIDs, timestamps, pointers, BLOB payloads or raw bytes. Opening the BLOB internal
file establishes its length and ownership; no BLOB payload is read.

The projection explicitly says `framing_validation=not_observed` and
`root_identity=not_observed`. Byte zero is not a record boundary. A nonzero format
classification is not its exact value. Nothing silently reuses the PARAMS row
profile or assumes a filename codec, free-row policy, compression or root name.

Success means only `config_declarations_captured`. Extraction, mapping and layout
validation remain `not_run`; native byte equivalence remains `not_observed` and
native compatibility `not_claimed`.

## Limits and local verification

Projection cap is 2048 bytes, capture cap 12288 and report cap 32768 including the
newline. The dedicated budget test builds the complete envelope (all source
hashes, lifecycle arrays, failure context and cleanup gates), reserves the full
capture cap, and retains the existing limits. It does not merely total payload
fields. Current tests cover synthetic reader mechanics, exact admission, mode
exclusion, bindings, cleanup invalidation and conservative complete envelopes.
Run the focused tests without a native installation:

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config*.py' -v
```

## Next acceptance boundary

An explicitly reviewed native observation must first establish actual CONFIG
declarations on the owned generated fixture. Independently reviewed evidence can
then justify one bounded storage/filename hypothesis. Root-file extraction,
logical metadata grammar and public BSL managers are separate subsequent steps.
The existing fixture's applied-v1 / loaded-unapplied-v2 / applied-v2 states can
later discriminate applied metadata; this baseline declaration capture does not
claim to do so. No production configuration, arbitrary database or supplied
binary is accepted by the oracle.
