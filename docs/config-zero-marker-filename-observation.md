# Bounded zero-marker CONFIG filename-field observation

This is a separate **field-only hypothesis**, not an active-file enumerator or a
relaxed success result for the original strict framing experiment. It adds no
BSL database/metadata API, root selection, BLOB extraction or applied-state
support. Its standalone reader retains `native_acceptance=pending`; synthetic
success is not native format evidence.

The original [strict profile](config-framing-observation.md) and function remain
unchanged. Genuine run [40255869028](https://github.com/Atridis/yadinassi/actions/runs/40255869028)
failed with `config_nonreserved_slot`. The separately audited [marker census](config-marker-census.md)
on run [40261287269](https://github.com/Atridis/yadinassi/actions/runs/40261287269),
head `008b2b9a91ca8d90d7cac55525ce50ed894b61e2`, tree
`30982a9529001b179a675e2a6fbfa8cbd97de5c7`, observed 16 candidate positions,
first marker one, and later zero14/one1/other0. It accepted no filenames,
free-chain model, framing, root or applied configuration. Those counts and
lengths are **not expectations** in this new recipe, nor evidence rebound to it.

## Independently pinned source basis

Primary Tool1CD source is pinned to the single commit
`d5e31816f4c9b11a445f73fc92d08803840ce599`:

- [TableRecord.cpp:95–98](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableRecord.cpp#L95-L98),
  blob `7ded7bf9508678f5b8fae622041b864bc3f1ec9e`: any nonzero first byte
  satisfies the removed predicate, not just the value one.
- [TableFiles.cpp:86–99](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableFiles.cpp#L86-L99),
  blob `2bf5d5f02bab1a7c0925af6193c16f2159da0eb8`: that predicate is checked
  before ordinary fields. Importantly, upstream then also checks BLOB pointer /
  length and nonempty name. **Zero marker is not active-file eligibility.**
- [Table.cpp:418–447](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L418-L447),
  blob `3b5d0dfd2a5e19faac7fda6c12ade6d70472c5f7`: field placement starts
  after one marker byte and data length must be a multiple of record length.
  [Lines 2085–2092](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L2085-L2092)
  initialize the first slot with marker one. Free-list links are separate;
  this observation never reads or validates them.
- [FieldType.cpp:138–157](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L138-L157),
  blob `6137a2e3fe433c456a5370abac10c049872fe7fb`: primitive width rules.
  [Lines 684–691](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L684-L691)
  use a two-byte length prefix before Unicode conversion. Our explicit unsigned
  little-endian count, maximum128 and strict surrogate rejection are a bounded
  supported hypothesis, **not a claim that upstream applies the same checks**.
- [Field.cpp:65–68](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Field.cpp#L65-L68),
  blob `6ba11ab55302535c2e60ac4fe1361131c7d314f7`: nullable fields add a
  byte; the exact admitted declarations have no nullable fields.

These are pinned source facts, not an official format specification. No upstream
implementation was copied, translated or executed. Checking every zero-marker
filename field is intentionally a falsifiable structural hypothesis. Unlike
TableFiles, this observer does not inspect BLOB pointers to discard otherwise
zero-marker candidates first.

## Exact profile and read boundary

`ConfigZeroMarkerFilenameProfile` requires the same seven ordered declarations,
string recordlock `0`, and integer format `0` as the unchanged strict profile;
Booleans are not integers. Widths258/7/7/3/11/8/6 after the status byte give a
candidate stride301. The FILENAME field starts at offset1 and occupies258 bytes.
The independently literal policy recipe agrees with the core recipe:

- identifier `config_zero_marker_filename_8380_8192_v1`;
- SHA-256 `8de171031a518dc9ac6446dd9425118be1d1d7151ff87607b93086cd924e8d4b`.

One catalog reader selects exact ASCII-case CONFIG, with no CONFIGSAVE/PARAMS
fallback. Exact declarations are checked before opening selected data/BLOB
mappings. Ownership and cumulative catalog budgets are shared; the BLOB mapping
establishes ownership and logical length only, never reads its body.

Data must be nonempty, divisible by301, and contain at most4096 candidates.
The first marker must be one; its other300 bytes remain opaque. Every later
marker is examined. For a zero marker only, read two length bytes at offset1,
require at most128 code units, then read precisely that many UTF-16LE units at
offset3 and decode strictly. No unused padding is read. Every nonzero candidate
has its other300 bytes left opaque, regardless of whether its marker is one or
another value. No ordinary numeric/date/attribute/pointer/part-number fields,
free-list links, filename identity or BLOB body are interpreted.

All zero-marker fields must validate, including the last one after valid
predecessors. Any malformed length, invalid encoding or short read fails the
whole observation, with a finite error code and no partial success. At least
one validated nonempty field is required: otherwise
`config_filename_no_nonempty_witness`. This is a local evidence-witness rule,
not a claim that native 1C prohibits empty names. Empty fields, NUL and BOM can
be structurally valid alongside the witness, without being accepted identities.
No normalization, case-folding, root matching or content-based selection occurs.

## Finite output and unchanged safety boundary

Only recipe identity/digest, selected logical lengths, candidate/class counters,
validated-zero/empty/nonempty counters and maximum code-unit count are exported.
No names, name hashes, raw bytes, row indices, marker positions, pointers or
arbitrary exception text survive. Exact primitive types and conservation hold:

- `candidate_slots = 1 + later_zero_count + later_one_count + later_other_count`;
- `data_logical_bytes = 301 * candidate_slots`;
- `validated_zero_count = later_zero_count = empty_filenames + nonempty_filenames`;
- `nonempty_filenames >= 1`, `1 <= max_filename_units <= 128`;
- selected data plus BLOB logical lengths fit the bound postimage.

`framing_validation=not_accepted`,
`filename_validation=zero_marker_bounded_utf16le`, and
`root_identity=not_observed` remain mandatory. The filename class refers only
to the selected fields, not whole-row framing or file identities. Extraction,
mapping and layout validation remain unrun; byte equivalence is unobserved and
general native compatibility is unclaimed.

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --config-zero-marker-filename-observation --output native-db-oracle/report.json
```

The new explicit lane `owned_config_zero_marker_filename_v1` uses report13,
capture14 and invocation10. Its closed inventory is the existing21 metadata
sources plus the common reader and new policy: exactly23, replacing only the
policy member. Every older inventory and mode remains explicitly selectable,
including the failed strict experiment and marker-only census. The workflow
changes only its selector: same image, admission, permissions and artifact gate.

The existing baseline auditor's closed post-session frozen image is used; no
native command, clone or lifecycle stage is added. Source/core/policy digests,
nonce/token, origin and postimage remain bound. All13 stages,11 snapshots,
five comparisons and four cleanup gates remain required; later failure
invalidates earlier field observation. The original private images are neither
retained nor reused.

Limits remain projection2048 / capture12288 / report32768 bytes. Maximal actual
projection is593 bytes; full projection cap fits a2998-byte capture bound.
The complete report with full capture cap and newline is31423/32768, margin1345.
These include the whole existing lifecycle and complete source provenance,
not merely the new payload. Catalog read/work/allocation budgets stay cumulative;
callers may lower, never raise, the4096 candidate/record-byte ceilings.

## Verification before any native acceptance

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config_zero_marker_filename*.py' -v
```

Synthetic tests cover all256 marker values, opaque nonzero payloads, exact reads,
zero/one/127/128/over-limit lengths, strict surrogate pairs and errors, page
crossings, late failures, the nonempty witness, ownership and cumulative budget
limits. No fixed native fixture is needed. Mutation controls cover counts/types,
extra payloads, old schemas, source/image/nonce/origin/postimage substitutions,
all mode exclusions, staged-only cold validation and later cleanup failure.
Original strict and census tests remain unchanged and run independently.

Freeze the source/profile/policy and complete finite bounds before a fresh native
capture. Independently authenticate its exact head/tree/ordered graph,23 source
pins, executed command, artifact/ZIP/log, final production validation and finite
report; green status alone is insufficient. A failing hypothesis remains failed,
not tuned after seeing its capture. Only this field-level hypothesis on that
owned image could be accepted. A later bounded file-entry/BLOB/root reader and
applied-vs-unapplied discrimination still require separate evidence.
