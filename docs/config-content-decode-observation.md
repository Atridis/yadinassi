# Bounded private single-part CONFIG content decoding

This separate experimental oracle lane advances beyond
[exact stored-byte chain transport](config-blob-chain-observation.md). Every
selected entry must satisfy one frozen single-part/name policy, then its exact
stored bytes are privately passed through or decoded as one complete raw-DEFLATE
stream. Only finite counters leave the operation. There is no public byte sink,
new BSL/runtime API, metadata parser, root identity or applied-state selection.
Synthetic success is not native acceptance; the producer returns
`native_acceptance=pending`.

## Source-informed hypothesis, deliberately narrower admission

The implementation facts below are pinned to Tool1CD commit
`d5e31816f4c9b11a445f73fc92d08803840ce599`, not an official portable specification.
No upstream implementation is copied, translated, imported or executed.

- [ConfigStorage.cpp:258–332](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L258-L332)
  concatenates stored parts before optional inflation. This first slice rejects
  **every selected nonzero part**, rather than pretending part zero is complete.
- [TableFiles.cpp:86–133](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableFiles.cpp#L86-L133)
  groups lowercase names and overwrites repeated part descriptors. This lane
  rejects duplicate selected ASCII-folded names instead of reproducing last-wins.
- [ConfigStorage.cpp:352–375](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L352-L375)
  supplies the name-based plain exceptions: exact case-insensitive names
  `DynamicallyUpdated`, `SprScndInfo`, `DBNamesVersion`, `siVersions`; a leading
  `{`; any `fo_version` substring; final extension `INF` or `PF`. Otherwise the
  entry is classified as raw DEFLATE, including names without dots. There is no
  header sniffing, guessed text grammar, trial decoder or copy fallback.
- [String.cpp:117–165](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/SystemClasses/String.cpp#L117-L165)
  has explicit ASCII/Russian lowercase rules. This lane admits only U+0020 through
  U+007E, 1–128 UTF-16 units, folding ASCII A–Z only. It does not claim all native
  Unicode collation. Spaces are significant; no trimming, normalization, NUL
  termination or path interpretation occurs.
- [ConfigStorage.cpp:597–685](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L597-L685)
  transforms dynamic names before classification. Therefore final `.new` and any
  ASCII-insensitive `_dynupdate_` substring are rejected before chain/decode work.
  The exact `DynamicallyUpdated` plain exception is not parsed or applied.
- [UZLib.cpp:101–161](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/UZLib.cpp#L101-L161)
  uses raw DEFLATE. This lane additionally requires EOF and full source
  consumption, rejecting trailing bytes and concatenated streams. That is stricter
  local admission, not a native-corruption verdict.

All inherited declaration/recordlock/format, stride 301, reserved marker,
zero-marker UTF-16LE, selection, locator, canonical PARTNO, exact-chain length,
zero-used tail and no-sharing rules remain. Nonzero-marker payloads, excluded
PARTNO, dates, attributes, DATASIZE and padding are not interpreted.

## Single attempt and shared resource graph

One `CatalogReader` opens the selected data/BLOB mappings once. The entire row
scan and all selected name/part/duplicate/dynamic guards finish before the first
chain read. At most 4095 private `(start, length, class)` tuples and folded keys
are retained. Each selected key/tuple reserves `512 + 8*units` additional output
weight and `4*units` work before normalization/comparison. Original names are not
retained alongside keys. Removing objects never refunds budget.

One unchanged `_ConfigBlobChains` reads each selected exact chain once. The new
private decoder binds to that chain primitive's **identical shared budget**; it
never calls the old public observer, reopens the image or resets an allowance.
Plain output aliases the existing immutable stored bytes; packed output is one
separately reserved immutable decoded result. The consumer counts successful
content and drops both buffers before continuing. A failed decode poisons the
operation and invalidates all counters; there is no retry or partial success.

All limits are conjunctive, lowerable only, and local resource hypotheses:

| Dimension | Ceiling |
|---|---:|
| Selected entries/keys | 4095 |
| Stored bytes per entry / total | 1 MiB / 4 MiB |
| Chain hops per entry / total | 8192 / 32768 |
| Plain or decoded bytes per entry / total | 4 MiB / 8 MiB |
| Decompress calls per packed entry / total | 4096 / 16384 |
| Input / returned-output chunk | 32768 / 65536 bytes |
| Decoder state weight per instance | 131072 bytes |

The default catalog limits remain unchanged, including 64 MiB reads, 128 MiB
processed work, 16 MiB BLOB bytes and 32 MiB cumulative output weight. Every new
charge intersects what remains after catalog/mapping/scan/chain work. Independent
maxima are not promised to fit simultaneously. The image cap remains 64 MiB.

Only `zlib.decompressobj(wbits=-15)` is used, with no dictionary. State weight is
reserved before construction. Each new input slice is charged before allocation;
fresh bytes are never appended to an unconsumed tail. Both call budgets increment
before each call. If `remaining` is the smaller remaining entry/total content
allowance, `max_length=min(65536, remaining+1)` is always positive and finite.
The extra byte is only an overflow probe. Before calling, reserve
`2*max_length + 2*len(pending)` output weight and
`len(pending) + max_length` work. Final immutable copying is separately charged.

Success requires EOF, empty unused data, empty unconsumed tail and the cursor at
the stored buffer end. Bounded empty-input calls may drain buffered output; no
EOF/output/input consumption is a finite truncated/nonprogress rejection.
One-shot `decompress`, `flush`, wrapper detection, fallback, concatenation and
recursive decoding are forbidden. Valid empty decoded streams are admitted as
individual entries, but cannot provide the mandatory positive decoded witness.
Raw DEFLATE has no wrapper checksum; its successful decoding does not establish
native semantic correctness, authenticity, exact internal zlib heap/CPU use, or
canonical final-bit padding. Finite input/output/calls, a fixed window and the
unchanged isolated outer deadline bound the experiment.

## Closed counters and truthful status

In addition to all inherited structural/chain summary fields, only six counters
are added: plain entries P, packed entries R, positive decoded entries V, plain
bytes A, inflated bytes U and inflate calls C. Let selected/completed chains be K
and stored bytes D. Exact integer (not Boolean) validation requires:

- `K = selected_part_zero_count >= 1`; selected nonzero parts are zero;
- `P+R=K`, `R>=1`, `1<=V<=R`, `R<=C<=min(16384,4096*R)`;
- `P=0` iff `A=0`; `P<=A<=P*1MiB`; `R<=D-A<=R*1MiB`;
- `V<=U<=V*4MiB`; `A+U<=8MiB`;
- every inherited marker/name/selection/chain conservation and capacity bound.

Compression class is `selected_singlepart_ascii_name_rule_raw_deflate_v1`;
top-level decompression status is `selected_singlepart_raw_deflate_observed`
only after successful capture, and is discarded/failed with the same lifecycle
gates. Framing stays unaccepted; extraction/mapping/layout stay unrun; root/file
identity, applied state and native byte equivalence stay unobserved. Names,
payloads, payload hashes, pointers, per-entry values and arbitrary exception text never
leave the operation. Per-entry exact content bytes/caps remain producer-source
facts, not reconstructible from aggregate counters alone.

## Explicit lane and frozen envelope

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --config-content-decode-observation --output native-db-oracle/report.json
```

The lane is `owned_config_content_decode_v1`, report 17 / capture 18 / invocation
13. Recipe `config_content_decode_8380_8192_v1` has SHA-256
`2afa62880be57cae787c9eafb4ccc0dc3022f1560e2becc418bc5e64efb31a3e`.
Exactly 23 sources are staged: the existing 21 metadata sources, common CONFIG
reader and one replacement closed policy. No broad named-file/PARAMS extraction
module is imported or staged. Every old explicit lane remains closed/available.

The reviewed workflow changes only its selector. Admission, genuine image,
network isolation, 2400-second runtime, 50-minute job, 13 stages, 11 snapshots,
five comparisons, three artifacts and four cleanup gates remain unchanged.
There is no new native command, clone or lifecycle phase. Read-only observation
uses the auditor's closed post-session frozen image on the same borrowed
anchored descriptor. Later lifecycle or cleanup failure discards the capture.

Caps stay **2048 / 12288 / 32768 bytes** for projection/capture/report. The full
rectangular projection bound is 1476 bytes; full projection-cap capture is 2992
bytes. All 23 source paths, provenance/context fields, lifecycle gates, artifacts,
the full capture cap and final newline total at most **31463 bytes**, leaving
1305 bytes. No measured image was used to widen or fit these bounds.

## Verification and separate native gate

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config_content_decode*.py' -v
```

Pure tests cover private byte equality and adversarial streams, all name/part
restrictions, resource intersections, finite counter mutations, complete report
bounds, every old lane's isolation, exact cold 23-source imports, frozen same-
descriptor postimage, bindings and every cleanup gate. Passing them is not native
compression evidence. The core suite includes independently literal stored,
fixed-Huffman, dynamic-Huffman, empty and multiblock streams, binary/non-UTF8
byte equality, real pending-tail/chunk transitions, exact 4 MiB and aggregate
8 MiB boundaries, all 4095 unique selected names with a real positive decoder
witness, a strictly positive one-byte overflow probe, final-copy
reservations and poisoned-chain rejection without another read. It also pins
the old reader's complete 30-node AST and verifies cold old-mode import without
zlib; it does not silently replace old-mode regression coverage.

Fresh exact-source native execution and producer audit
must show **at least one completely consumed raw stream with positive decoded
bytes**, with every selected entry passing. No previous count/length/name list
is expected. If P is zero, plain pass-through has only synthetic coverage for
that image. No independent native decoded-byte equivalence is claimed.

Publication/run remain separate reviewed-ref admission gates: actual head/tree,
ordered executed jobs/command, every source pin, recipe, genuine image/native
identity, sole hardened report ZIP, exact report bytes, production final validator
and all lifecycle/cleanup checks must be rebound. A failed frozen hypothesis is
terminal, not grounds to enlarge limits or retry with fresh budgets. A successful
narrow decode enables a later separately designed root/content-structure slice,
not an unbounded metadata census or automatic multipart/applied-state support.
