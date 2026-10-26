# Private CONFIG locator-to-entry reference

A separate experimental oracle lane consumes the selected fixed key `root`,
parses one complete narrow locator, and uses its private GUID to select exactly
one other admitted CONFIG entry. That target must completely decode to positive
content. All remaining selected entries still complete exact chain and content
decoding. Only finite counters/classes leave the operation.

This establishes a content-derived selected-entry relation on one frozen image,
**not** semantic configuration root identity, applied configuration, metadata
object identity, native decoded-byte equivalence or general CF compatibility.
The source-bound producer reports `native_acceptance=pending`. Genuine execution
and independent producer/report audit remain separate acceptance gates.

## Source facts and local hypothesis

No upstream implementation is copied, translated, imported or executed. These
pinned public implementations are evidence, not official native specifications:

- DaJet [`ConfigFiles.cs`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/constants/ConfigFiles.cs)
  defines `root`. [`OneDbMetadataProvider.cs:667–679,714–718`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/OneDbMetadataProvider.cs#L667-L718)
  opens CONFIG/root, obtains a GUID, then opens CONFIG with that GUID filename.
  [`RootFileParser.cs`](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/RootFileParser.cs)
  reads child position 1 and cancels parsing. It is an SQL-backed convention, not
  proof of this grammar on a file database. Early cancellation, permissive UUID
  fallback, stream sniffing and row overwrite are not adopted.
- Tool1CD [`ConfigStorage.cpp:413–464`](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L413-L464)
  resolves a top-level name to a table ContainerFile; a nested catalog is opened
  only for an explicit remaining path. A decoded CONFIG entry is not assumed to
  be a catalog merely because other contexts use catalogs.
- [`save_depot_config.cpp:257–269,414–435`](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/save_depot_config.cpp#L257-L435)
  emits the modern two-child root, prefixes UTF-8 BOM and raw-deflates it under
  outer `root`. The extra root-map children are populated only in the older
  branch. That older branch uses `{1,GUID,count,...}` under `metadata/root` and
  is not admitted. [`Parse_tree.cpp`](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Parse_tree.cpp)
  emits GUIDs bare; its broader parser behavior is not adopted.

Combining that writer shape and independent SQL reference consumer with our
admitted file-DB CONFIG namespace is a **new local hypothesis**. Mandatory BOM,
exact tag `2`, full EOF and a 1024-byte parser cap are deliberately narrower
admission. They are not asserted universal native facts or corruption criteria.
No captured UUID, filename list, native count or byte total enters the selector,
profile or expected outcome. The only fixed selector is the public key `root`.

## Complete private grammar and diagnostics

```text
root := EF BB BF ws "{" ws "2" ws "," ws guid ws "}" ws EOF
ws   := zero or more ASCII bytes 20 09 0D 0A
guid := 8hex "-" 4hex "-" 4hex "-" 4hex "-" 12hex
hex  := ASCII 0-9 A-F a-f
```

The deterministic byte scan materializes only a fixed 36-byte key, folding ASCII
A–F to lowercase. It makes no full decoded-string copy, general AST or UUID
version/variant/nonzero inference. Exactly one initial BOM is required; interior
or repeated BOMs, old/alternate tags, quoted/nested/wrong-width GUIDs, NUL,
non-ASCII whitespace, comments, extra fields and non-whitespace tails reject.

The parser accepts 43–1024 bytes. `ConfigRootReferenceLimits.max_input_bytes` is
an exact integer from 1 through 1024 (not Boolean), lowerable only. The unchanged
content decoder may already allocate up to 4 MiB **before** this parser length
check. This is not an early 1024-byte inflation cap.

New finite codes are `config_root_missing_selected_root`,
`config_root_missing_selected_target`, `config_root_bom`, `config_root_tag`,
`config_root_grammar`, `config_root_guid`, `config_root_trailing`,
`config_root_input_bytes`, `config_root_input`, `config_root_failed_attempt`, and
`config_root_empty_target`. The policy freezes their exact categories. Precedence
is operation-use guard; immutable-byte type/length; BOM; opening brace; exact tag
and delimiter; comma; exact bare GUID; closing brace; trailing whitespace/EOF.
A non-delimited tag `2` is a tag error; an overlong GUID token is a GUID error;
a comma after a complete GUID fails the closing-brace grammar. Root presence is
checked after the entire guard scan and before any chain read. Target presence
follows complete root parsing; target emptiness follows strict completed decode.
Inherited errors retain their closed codes/categories. No private key, byte,
offset, snippet or raw parser/zlib/OS exception text enters diagnostics.

## One graph, one attempt, explicit prepaid storage

One inherited `CatalogReader` construction performs its existing bounded,
charged header/root-map setup. Its budget is then available: reserve 1024 output
weight **before constructing any new root-operation state**. There is no claim
of reservation before the inherited reader constructor. The private operation
marks itself used before catalog reading, scan, map/parse/lookup or chain work.
The previous 60,997-byte reader prefix and all previous profiles/APIs remain
unchanged; no old observer is called for a second traversal.

The entire inherited scan, selected name/part/dynamic guards and folded-name
uniqueness finish before any selected chain read. The unchanged classifier owns
its guard-key set; a distinct folded-name map retains at most 4095 selected
`(start,length,class)` tuples. Before each second normalization/map insertion,
reserve output weight `512 + 8*units` and work `4*units + 32`, in addition to all
inherited charges. Drop the guard set after scanning, without a refund.

One unchanged chain helper and decoder share the reader's identical budget and
physical/logical ownership. Pop root, read/decode/fully parse it once, and drop
its buffers. Pop the content-derived GUID target, read/decode it once, require
positive bytes, and drop its buffers. Traverse all remaining map values in
insertion order exactly once. There is no row-order predecode, payload cache,
second read, sorting copy, reopened image, new context, reset or refund. An
unrelated late failure invalidates the entire observation.

Before parsing L admitted bytes reserve work `4*L + 128` and output weight 512;
before each map lookup reserve work 256 and output weight 128. Reserve 4096
output weight before the final observation. The slotted operation has fixed
state; these are conservative explicit accounting weights, not measurements of
Python/native heaps. They intersect remaining existing global budgets.

Any parse, lookup, resource, decode or chain failure makes the wrapper unusable
and poisons every constructed shared decoder/chain helper. A successful prior
inflation cannot be reused after a failed parse. A repeated operation call does
no read, budget reset or partial-return work.

All inherited limits remain: selected 4095; stored 1 MiB per entry/4 MiB total;
hops 8192/32768; decoded 4 MiB/8 MiB; inflate calls 4096/16384; input/output
chunks 32768/65536; global reads 64 MiB, processed work 128 MiB, blob bytes 16 MiB,
output weight 32 MiB. They are conjunctive; independent maxima need not coexist.
Selected logical-block sharing and forbidden physical role/map overlap fail;
**distinct logical BLOB blocks on the same physical page remain valid**. Every
zero-used tail is followed, even after the declared payload length is reached.

## Closed witness, transport and tests

Add only `parsed_locator_count=1`, `resolved_positive_target_count=1`, and
`relation_validation=fixed_key_guid_reference_resolved_v1` to inherited content
counters. Distinct locator and target both use the frozen raw-DEFLATE name rule.
For selected K, raw R, positive raw V and inflated bytes U: `K>=2`, `R>=2`,
`V>=2`, `V+42<=U<=1024+(V-1)*4194304`, and maximum selected filename width
at least 36, as well as all previous arithmetic/conservation and the unchanged
8 MiB total decoded cap. In particular `U>=44`. Per-entry
positivity/full parsing are source-bound producer facts, not independently
recoverable from aggregate counters. Keys, payloads, per-entry lengths, offsets
and private payload hashes never escape. Required public source/image provenance
hashes remain present.

Explicit CLI selector `--config-root-reference-observation` (internal mode
`config-root-reference`), lane
`owned_config_root_reference_v1`, profile `config_root_reference_8380_8192_v1`,
report/capture/invocation schemas 19/20/14. Canonical recipe SHA-256:
`df07907176f55bb17c3ed086173da9549f05a0d44a63a934faee12e3829467c5`.
Exact cold closure is the existing 21 metadata sources, common reader and new
closed policy: 23 files, no broad PARAMS/DBNames/named-file extraction import.
The borrowed anchored post-session image, pinned genuine image, no-network and
UID/GID/read-only isolation, 2400-second execution/50-minute workflow limits,
13 stages, 11 snapshots, five comparisons, three artifacts and four cleanup
gates remain unchanged. Any lifecycle/cleanup failure discards capture.

New independently derived rectangular projection bound is 1597/2048 bytes. The
complete report envelope, including all 23 source paths, provenance, context,
lifecycle/artifacts, full 12288-byte capture and final newline, is 31463/32768
(margin 1305). Its equality with the previous number is incidental, not reuse of
the old proof. Finite failures, both complete production success/failure reports
and cold import/read/final validation are covered by focused synthetic tests.

The parser corpus includes all truncations, every GUID character position,
43/1024-byte boundaries and deterministic overlapping-error precedence. Full
synthetic integration covers root/target every row order, missing/excluded and
duplicate selected names, empty target/unrelated content, late chain/decode
failure, same-page valid ownership and illegal overlap, exact consumed ordering,
shared-budget identity, preallocation, no-refund and poisoned repeat attempts.

A future genuine witness must bind exact source/recipe/image/postimage/lifecycle
and demonstrate this content-derived one-hop path without exporting private
bytes. Another grammar, absent key/target, empty target, cap exhaustion or strict
failure is terminal for this frozen hypothesis. No payload-driven fallback,
alternate-root search, expected UUID patch, fresh-budget retry or native-semantic
claim is allowed. Target metadata parsing and applied-state choice are separate
future slices.
