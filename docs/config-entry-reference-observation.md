# Bounded CONFIG entry-reference prerequisites

This separate **prerequisite observation** is not a CONFIG file reader, a chain
validator or applied-configuration support. It adds no BSL/runtime API. Its
standalone reader keeps `native_acceptance=pending`: synthetic success is not
native evidence. The original [strict framing](config-framing-observation.md),
[marker census](config-marker-census.md) and [zero-marker filename](config-zero-marker-filename-observation.md)
profiles, policies and selectors remain unchanged and separately selectable.
A prior capture does not establish this new hypothesis.

## Pinned source facts and deliberate restrictions

Tool1CD is pinned to commit `d5e31816f4c9b11a445f73fc92d08803840ce599`.
These are primary implementation facts, not an official portable format
specification; no upstream implementation is copied or executed.

- [TableFiles.cpp:86–115](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableFiles.cpp#L86-L115),
  blob `2bf5d5f02bab1a7c0925af6193c16f2159da0eb8`, excludes removed/nonzero
  markers, then either-zero BLOB components, then empty names, before reading
  PARTNO. Later grouping is a separate operation, not reproduced here.
- [Common.h:44–49](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Common.h#L44-L49),
  blob `00020894695f25437029f001357f3aa9d5b6e9fb`, declares two uint32 members,
  start followed by length. [TableRecord.h:46–54](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableRecord.h#L46-L54),
  blob `43815a00319dfc0b32ae246adf602ca5571fcf62`, uses native reinterpret-cast
  conversion. Our explicit u32LE interpretation is an admitted-format
  hypothesis, **not** a claim that those casts specify portable endianness.
- [Table.cpp:729–788](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L729-L788),
  blob `3b5d0dfd2a5e19faac7fda6c12ade6d70472c5f7`, checks 256-byte block
  alignment and block bounds; a six-byte header leaves at most250 payload bytes.
  This observer uses only necessary capacity bounds, not that chain algorithm.
- [FieldType.cpp:447–464](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L447-L464),
  blob `6137a2e3fe433c456a5370abac10c049872fe7fb`, and
  [BinaryDecimalNumber.cpp:47–77](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/BinaryDecimalNumber.cpp#L47-L77)
  and [186–203](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/BinaryDecimalNumber.cpp#L186-L203),
  blob `91ff9fe065fa8116b9318792a4678d95128eae56`, motivate signed decimal
  nibbles. Upstream accepts any nonzero sign nibble as positive and uses
  `ToIntDef`; canonical sign1/padding0 and the part4095 ceiling are explicitly
  narrower resource/encoding restrictions, not native equivalence.
- [ConfigStorage.cpp:578–688](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L578-L688),
  blob `3ec4e3ed0101b8a792a162c3111547af28de45b2`, handles dynamic updates at
  another layer. Matching a name or seeing a locator cannot establish the
  applied configuration.

## Exact hypothesis and read boundary

`ConfigEntryReferenceProfile` retains the seven exact ordered declarations,
string recordlock `0`, integer format0 (not a Boolean), candidate stride301,
exact ASCII-case CONFIG selection without fallback, and at most4096 candidates.
The first marker is exactly one; its remaining300 bytes are opaque. Later
nonzero markers are counted without reading their payloads.

Every later zero-marker FILENAME must validate, even when its reference will be
excluded: u16LE code-unit count at offset1, at most128 units, strict UTF-16LE at
offset3. Unused field padding is not read. Empty, NUL and BOM-containing names
are structural strings, not accepted identities. No normalization, matching,
case-folding or grouping occurs.

For every zero-marker candidate, BINARYDATA occupies offset287/width8 and is
interpreted as u32LE start followed by u32LE packed length. Either-zero
components are excluded first. Among remaining candidates, empty names are
excluded. Only nonempty names with both components positive are selected.
Excluded PARTNO bytes remain unread. Positive but out-of-range components on an
empty-name candidate are excluded, not validated references.

The logical BLOB mapping must have length divisible by256 and at least512.
With `B = blob_logical_bytes / 256`, every selected reference must satisfy:

- `1 <= start < B`;
- `1 <= length <= min(2**32 - 1, 250 * (B - 1))`.

This proves **necessary capacity only**: no BLOB block header or payload is read, no
allocation depends on declared length, and no chain ownership, cycles,
termination, exact assembled length or readability is established. Separate
catalog mapping ownership and cumulative budget checks remain in force.

Selected PARTNO occupies offset295/width6: high sign nibble1, ten high-first
decimal digits each0..9, low final padding nibble0, and decoded value0..4095.
All selected candidates must pass, including the last after valid predecessors.
At least one selected positive-reference **part-zero witness** is required;
otherwise `config_reference_no_part_zero_witness`. Duplicate or noncontiguous
part numbers are not grouped or rejected. The witness does not prove a file.

DATASIZE, dates and attributes remain opaque. In particular, DATASIZE is not
equated with packed BLOB length. There is no filename, slot-count, reference-count
or part-count expectation derived from a native capture.

The independent core and policy recipes have identifier
`config_entry_reference_8380_8192_v1` and SHA-256
`927f3c22e999831d799b14d1a0f6b23a129af241646f3b405e19b9d8b9457d35`.

## Closed finite output and lifecycle

Only recipe identity, logical lengths, marker/filename structural counters,
selection/exclusion counters and fixed classes are exported. No names, name
hashes, record positions, pointers, per-record length/part lists, raw bytes or
arbitrary exception text survive. Exact primitives exclude Booleans as integers.
Existing marker/filename conservation remains, plus:

- `validated_zero_count = reference_excluded_count + empty_name_excluded_count + selected_reference_count`;
- `selected_reference_count = selected_part_zero_count + selected_part_nonzero_count`;
- `empty_name_excluded_count <= empty_filenames`;
- `selected_reference_count <= nonempty_filenames`;
- `selected_part_zero_count >= 1`.

Reference exclusions may include empty names; name exclusions count only names
whose reference components are both positive. These disjoint exclusion classes
are not file eligibility claims. Mandatory classes remain
`framing_validation=not_accepted`, `filename_validation=zero_marker_bounded_utf16le`,
`locator_validation=selected_capacity_bounds_only`,
`partno_validation=selected_canonical_bcd_0_4095`, and
`root_identity=not_observed`. Chain traversal, decompression, extraction,
applied-state interpretation and general native compatibility remain unaccepted
and unrun; no free-chain model is inferred.

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --config-entry-reference-observation --output native-db-oracle/report.json
```

The explicit lane `owned_config_entry_reference_v1` uses report14/capture15/
invocation11. Its closed inventory is the existing21 metadata sources plus the
common CONFIG reader and this policy: exactly23, replacing the policy member
rather than accumulating policies. The workflow changes only the selector;
image, security/admission, artifact gates and all13 stages,11 snapshots,
five comparisons and four cleanup gates are unchanged. It observes the existing
owned baseline auditor's closed post-session frozen image. No native command,
clone or lifecycle stage is added. Later failure discards an earlier observation.

Caps stay projection2048/capture12288/report32768. An independent conservative
rectangular projection envelope is857 bytes: each integer is charged at its
maximum decimal width even if those maxima cannot coexist. The full projection
cap yields a2993-byte capture bound. The complete report, including the full
capture cap, all source paths, lifecycle and final newline, is31398 bytes,
leaving1370. Reader work/read/allocation limits remain cumulative; callers may
lower, never increase, the4096 slot/record-byte ceilings.

## Verification and native acceptance gate

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config_entry_reference*.py' -v
```

Synthetic tests cover all256 marker values, filename and locator page crossings,
UTF-16 failures even on reference-excluded candidates, reference-endian/bounds
controls, alignment and capacity boundaries, every invalid sign/digit/padding
nibble, part4096, excluded PARTNO opacity, the positive part-zero witness,
late failures, cumulative budgets, closed counts/types/classes, source/image/
nonce/origin/postimage substitutions, every older selector, staged-only cold
validation and later cleanup failures. They establish implementation properties,
not native format support.

Freeze the source/profile/policy and finite bounds before fresh native capture.
Independently bind exact head/tree and live ordered execution graph, all23 source
pins, invocation, report, hardened ZIP/log, final production validator and cleanup.
Green CI alone cannot accept this observation. A failed hypothesis remains failed;
it must not be tuned to a capture. Root/framing/free-chain/file identity/applied
state remain unaccepted even after successful prerequisite evidence. A subsequent
exact-length bounded BLOB reader needs a separate frozen hypothesis and evidence.
