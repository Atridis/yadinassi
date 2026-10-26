# Bounded CONFIG candidate-marker census

This is a **diagnostic observation**, not a more permissive framing reader.
The preceding strict experiment remains failed: [native run
40255869028](https://github.com/Atridis/yadinassi/actions/runs/40255869028), head
`d6553aebc2d1c2e1c00e2edea5e5db69b2dc12c7`, tree
`7831e093f255f125c279fc44711880e456189587`, emitted finite
`config_framing_failed / unsupported_layout / config_nonreserved_slot`.
It did not establish complete row framing, filename validation or root identity.
The original [strict framing profile](config-framing-observation.md), recipe
`48fc146c1e748b877b518993d09e7050f4c57cd6cd8682596f97411655c4a7e3`, and strict
function are retained unchanged. Nonzero later markers still fail that function.
No previously captured report is relabeled as diagnostic success.

## Why a separate observation

Primary Tool1CD sources at commit
`d5e31816f4c9b11a445f73fc92d08803840ce599` distinguish a read predicate from
free-list management:

- [TableRecord.cpp lines 95–98](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableRecord.cpp#L95-L98),
  blob `7ded7bf9508678f5b8fae622041b864bc3f1ec9e`, tests any nonzero first byte
  as removed; this is not a restriction to the value one.
- [Table.cpp lines 2321–2326](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L2321-L2326),
  blob `3b5d0dfd2a5e19faac7fda6c12ade6d70472c5f7`, and
  [TableFiles.cpp lines 86–91](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableFiles.cpp#L86-L91),
  blob `2bf5d5f02bab1a7c0925af6193c16f2159da0eb8`, skip that class before
  interpreting ordinary fields.
- [Table.cpp lines 2007–2022](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L2007-L2022)
  mark a row by writing one without interpreting fields or updating indexes.
  [Lines 2085–2102](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L2085-L2102)
  separately initialize the first slot and follow a link at offset one when
  inserting. A marker class is not proof of a reusable free slot or valid chain.

These are pinned source facts, not an official format specification. No upstream
implementation was copied, translated or executed. They motivate neutral counts,
not silently skipping rows until the earlier experiment passes.

## Frozen diagnostic recipe

`ConfigMarkerCensusProfile` requires the same exact seven ordered declarations,
string recordlock `0` and integer format `0` as the strict profile. The original
width calculation supplies a **candidate** stride of 301; Boolean values are
not integers. Its separate canonical recipe is
`config_marker_census_8380_8192_v1`, SHA-256
`a73b1d173b65726fd0d06a09bab112e0ab287fc9206f289538ce7169d93d80ba`.
This recipe is fixed before any new native capture and does not encode expected
marker counts, a native data length of 4816 or a candidate count of 16.

One catalog/ownership/budget graph selects only exact ASCII-case CONFIG; no
CONFIGSAVE/PARAMS fallback is attempted. Descriptor checks precede opening the
selected data and BLOB mappings. Data must be nonempty and divisible by 301,
with 1–4096 candidate positions. As before, both selected file mappings undergo
ownership checks, but BLOB bodies remain unread.

At every candidate boundary the observer reads exactly one status byte. It
returns the first marker's class and aggregate counts of later markers:
`zero`, `one`, `other`. All candidates are examined, including all nonzero
values. No candidate is called active, removed or free; no index or exact
nonzero value is returned. The first marker need not be one for this diagnostic
to complete. No row fields, filename length, UTF16 bytes, timestamps, numeric
values, pointers, links, part numbers or BLOB content are read.

The closed public projection contains fixed recipe identity/digest,
logical lengths, candidate stride/count, first marker class and three later
counts. Exact integer conservation is mandatory:

- `candidate_slots = 1 + later_zero_count + later_one_count + later_other_count`;
- `data_logical_bytes = 301 * candidate_slots`;
- selected data plus BLOB logical lengths do not exceed the bound postimage.

`framing_validation=not_accepted`, `filename_validation=not_run`, and
`root_identity=not_observed` are mandatory even when every marker would fit the
old hypothesis. Counts cannot validate either a free-list model or effective
applied configuration. Empty data is unsupported; a single candidate only
produces zero later counts, not evidence of a filename or root.

## Explicit mode and unchanged safety boundary

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --config-slot-marker-observation --output native-db-oracle/report.json
```

The reviewed workflow selects this diagnostic mode. Lane
`owned_config_marker_census_v1` uses report schema 12, capture schema 13 and
invocation schema 9. It stages exactly 23 files: the existing 21-source metadata
inventory, the common core and the new census policy. The old strict policy is
not staged; all older modes, schemas and inventory memberships remain explicit.
No additional native command, fixture, lifecycle stage or clone is introduced.
The existing baseline auditor's closed post-session frozen image is used.

Image digest/platform, locale/timezone, actor/branch/checkout admission,
permissions, report-ready gate and artifact destination are unchanged. Catalog,
core, policy and all-source hashes, operation nonce/token, origin and closed
postimage bind the capture. All 13 stages, 11 snapshots, five comparisons and
four cleanup gates are still required. Later failure discards prior observation.

Existing caps remain projection 2048, capture 12288 and report 32768 bytes
including newline. The complete finite report bound is 31388 (margin 1380),
including the full capture cap. The full projection cap fits inside a 2991-byte
capture bound; the maximal actual projection envelope is 466 bytes.
No arbitrary source strings, raw data, marker positions or exception text can
be exported. Source values and private native images are not retained.

## Evidence required before any acceptance

Synthetic coverage includes all 256 marker values, all first-marker classes,
count conservation, invalid filename bytes kept opaque, every candidate read,
last-read failure, alignment/ownership/cap limits, source and image substitutions,
all mode exclusions, cold staged validation and cleanup invalidation. The old
strict tests still require nonzero later markers to fail. Windows print-marker
tests accept only exact LF or CRLF; production report serialization is unchanged.

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config_marker_census*.py' -v
```

A fresh source-bound native run and independent finite audit are still required;
these tests and the earlier failed run are not census evidence. Freeze actual
head/tree/workflow, the 23 staged source hashes and recipe before capture. Verify
artifact framing, final production validation and independent mutation controls.
The only possible new acceptance is a marker census on that owned postimage.
Framing remains unaccepted, extraction/mapping/layout unrun, root/native bytes
unobserved and general native compatibility unclaimed. A separately justified
removed/free-slot model, filename framing and root/applied-state interpretation
must be proposed and validated later rather than inferred from these counts.
