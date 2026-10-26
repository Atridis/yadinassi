# Experimental bounded CONFIG framing observation

This separately selected observation lane adds no runtime/CLI/BSL metadata API,
root selection, extraction, multipart or applied-state support. Its standalone
stdlib-only core remains `native_acceptance=pending`; a fresh independently
audited native run is required before accepting this framing hypothesis on an
owned fixture. Synthetic tests and activation are not native evidence.

`--config-framing-observation` selects `owned_config_framing_observation_v1`,
report schema 11, capture schema 12 and invocation schema 8. The reviewed workflow now selects the separate [zero-marker filename-field observation](config-zero-marker-filename-observation.md); the [marker-only census](config-marker-census.md) also remains explicit.
This strict mode remains explicitly available without changing triggers, actor/checkout admission,
immutable image, rights, artifact destinations or report-ready gates. The old
CONFIG declaration mode remains explicitly available with its original closed
schemas and inventory. The new mode is mutually exclusive with every old mode.

## Genuine failed experiment

[Run 40255869028](https://github.com/Atridis/yadinassi/actions/runs/40255869028),
head `d6553aebc2d1c2e1c00e2edea5e5db69b2dc12c7`, failed at baseline with
`config_framing_failed / unsupported_layout / config_nonreserved_slot`. The
all-later-zero requirement was refuted on that owned postimage. This is not
framing/filename/root acceptance; the profile and strict function remain unchanged.
A separate diagnostic census must not turn that failure into success.

## Evidence and one falsifiable hypothesis

The independently audited declaration capture from
[run 40240681339](https://github.com/Atridis/yadinassi/actions/runs/40240681339),
head `706f11f9a1b9d49e5bbc302680289efe50d700f8`, tree
`60d6a5ebb7092f690a51ea031eaa30f037c42932`, admitted seven ordered declarations,
lock string `0`, integer-zero format, data length 4816, BLOB length 20992 and
initial data byte class one. It did **not** observe row boundaries or filenames.
The new source hashes cannot retroactively rebind that evidence.

The explicitly constructed `ConfigFramingProfile` accepts only:

| Field | Type | Null | Length | Precision | Case | Offset | Width |
|---|---|---:|---:|---:|---|---:|---:|
| FILENAME | NVC | 0 | 128 | 0 | CI | 1 | 258 |
| CREATION | DT | 0 | 0 | 0 | CS | 259 | 7 |
| MODIFIED | DT | 0 | 0 | 0 | CS | 266 | 7 |
| ATTRIBUTES | N | 0 | 5 | 0 | CS | 273 | 3 |
| DATASIZE | N | 0 | 20 | 0 | CS | 276 | 11 |
| BINARYDATA | I | 0 | 0 | 0 | CS | 287 | 8 |
| PARTNO | N | 0 | 10 | 0 | CS | 295 | 6 |

Lock must be exact string `0`, format exact integer 0 (not Boolean). One status
byte plus these widths yields stride 301. No nullable/version prefix is admitted.
The canonical recipe includes the exact declarations, placements and finite
framing/codec/selection identifiers; its SHA-256 is retained with the result.

This hypothesis was independently derived from primary Tool1CD source pinned at
`d5e31816f4c9b11a445f73fc92d08803840ce599`, not an official specification:

- [Table.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L295-L300),
  blob `3b5d0dfd2a5e19faac7fda6c12ade6d70472c5f7`: hidden version insertion is
  conditional on recordlock; lines 418–447 establish status-first field placement
  and divisibility; lines 2085–2092 initialize reserved slot zero with marker one.
- [FieldType.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L138-L157),
  blob `6137a2e3fe433c456a5370abac10c049872fe7fb`: primitive width rules;
  lines 684–691 describe the length-prefixed Unicode field. Little-endian and
  strict decoding are explicit supported hypotheses, not host-endian inference.
- [Field.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Field.cpp#L65-L68),
  blob `6ba11ab55302535c2e60ac4fe1361131c7d314f7`: nullable fields add one byte;
  this admitted vector has none.
- [TableRecord.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableRecord.cpp#L95-L98),
  blob `7ded7bf9508678f5b8fae622041b864bc3f1ec9e`: nonzero status is removed.
  Our profile is deliberately narrower: slot zero must be one, all later slots
  must be zero. A later free slot **fails**; it is not skipped.

No upstream code was copied, translated or executed. Strict bounds and complete
scan are independent policy choices. Although 4816 is divisible by 301, neither
4816 nor 16 is an expected native value in code or acceptance. A fresh capture
can refute this profile. A failing capture must remain failed; do not tune the
profile against that capture to obtain a passing report.

## Read and output boundary

One CatalogReader finishes its catalog, selects exactly one ASCII-case-insensitive
CONFIG table, and checks exact declarations before opening selected files.
CONFIGSAVE/PARAMS and alternate names are never fallback candidates. Data and
BLOB mappings retain the same ownership and cumulative budget graph. BLOB
mapping establishes ownership/length only: **no BLOB payload is read**.

Data length must be nonzero and exactly divisible by 301. Slot zero's remaining
300 bytes are opaque. Each later slot has marker zero; its FILENAME uses a
little-endian u16 code-unit count at offset one, at most 128, followed by strict
UTF-16LE. Every filename is validated, including those after an otherwise valid
row. Empty strings, NUL and BOM are structurally Unicode, not semantically
accepted file identities. Surrogates must pair. Unused filename padding and
all dates, attributes, numeric fields, pointers and part numbers remain unread.

Only fixed identifiers, profile digest, logical lengths, slot/empty/nonempty
counts, maximum observed code-unit count and cumulative budget usage survive.
No filename, UUID, row, timestamp, pointer, raw byte or arbitrary exception text
is returned. Reserved-only data can satisfy framing with zero active slots; that
does not establish file presence. Counts obey `slots=active+1` and
`active=empty+nonempty`. This is not root identity or applied-state evidence.

The observer caps slots and record bytes at 4096 each; callers may only lower
those ceilings. Existing catalog read/process/output/ownership limits stay
cumulative. Temporary scalar reads, decoded filename validation and result
representation are reserved before allocation; profile construction is separate
fixed-size work done before any source read. No source callback is closed/written.
These are representation/work bounds, not exact Python heap or time guarantees.

## Synthetic verification and required next gate

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config_framing*.py' -v
```

Tests use independently literal declarations and offsets, vary slot counts,
cross backing pages, and reject malformed profiles, reserved/free markers,
alignment, length/surrogates, alias/duplicate tables, ownership overlaps and
resource overruns. They verify exact read ranges, no unrelated field/BLOB reads,
finite result content, frozen output and cold `-I -S -B` stdlib-only operation.
Synthetic tests do not establish the actual CONFIG storage profile.

The closed policy stages exactly 23 sources: the 21-source metadata observation
set plus the framing core and policy. No PARAMS extractor, DBNames parser, row
decoder or old CONFIG declaration policy is staged. Catalog/core/policy and
complete source-manifest hashes, nonce/token, platform/origin and closed
postimage bind the capture. Full frozen-source staging and cold imports are
verified; older inventories and validators remain closed.

The public projection excludes the core's budget-usage object and exports only
fixed identifiers/profile digest, logical lengths, counts and the three finite
framing/filename/root classes. Its validator conserves all counts and the exact
301-byte hypothesis relation, with exact primitive types and no extra keys.
The complete maximal report envelope is 31334/32768 bytes including newline
and the full 12288-byte capture cap (margin 1434); the full 2048-byte projection
cap fits within a 2985-byte capture bound. No cap was raised.
Later lifecycle or any cleanup failure invalidates a successful capture. Success
means only `config_framing_observed` on that owned frozen image, not general
record/layout acceptance or extraction. Errors are finite categories/codes.

Before any native run: independently review the complete new source inventory,
recipe digest and profile, verify maximal projection/capture/report envelopes
without raising existing 2048/12288/32768-byte caps, and test mode exclusion,
admission, all source/nonce/token/closed-postimage bindings, tamper controls and
later cleanup invalidation. Preserve immutable image, actor/branch admission,
native commands, 13 stages, 11 snapshots, five comparisons and four cleanup gates.
No native lifecycle addition is needed: inspect the existing closed frozen
baseline auditor postimage. It must be freshly produced, never an old private
database retained from the declaration run.

After publication, a reviewed fresh native operation is still required.
An independent auditor must bind exact head/tree/workflow/source hashes and
validate the final report from actual staged source. Maximum permissible outcome
is source-bound framing/filename hypothesis satisfaction on that one image.
Extraction/mapping/layout acceptance stay not run, root identity and native byte
equivalence unobserved, general compatibility unclaimed. Failure remains finite
and fail-closed; raw databases and markers still undergo producer cleanup.

Finally, even successful filename framing is not effective applied metadata:
[ConfigStorage.cpp](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L578-L688),
blob `3ec4e3ed0101b8a792a162c3111547af28de45b2`, has separate dynamic-update
selection behavior. Root extraction, dynamic updates, and applied-v1 versus
loaded-unapplied-v2 versus applied-v2 discrimination need later separate evidence.
