# Bounded exact stored-byte CONFIG chains

This experimental **all-selected stored-byte transport** is not a CONFIG named
file reader and adds no BSL/runtime API. It advances beyond
[entry-reference prerequisites](config-entry-reference-observation.md): every
selected positive reference is read completely to a zero terminator and its
exact stored bytes are assembled privately, then discarded. Only finite counters
leave the observer. Synthetic success is not native evidence; the core returns
`native_acceptance=pending` even after synthetic tests pass.

All earlier profiles, recipes, policies and explicit selectors remain unchanged,
including the failed strict whole-table framing hypothesis. This lane neither
accepts framing nor reuses a previous native capture as evidence for chain reads.

## Pinned implementation facts and local restrictions

The source basis is Tool1CD commit
`d5e31816f4c9b11a445f73fc92d08803840ce599`. These are implementation facts,
not an official portable specification; no upstream implementation is copied,
translated, imported or executed.

- [Table.h:32–33](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.h#L32-L33),
  blob `7f4f8bfddf622a3443d6db35511ea7c85cbe0c0e`, defines256-byte blocks with
 250 payload bytes. Its signed `int16` struct member is **not** the decoder.
- Actual [readBlob at729–788](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L729-L788)
  and [801–872](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L801-L872),
  blob `3b5d0dfd2a5e19faac7fda6c12ade6d70472c5f7`, accesses next-u32 at0,
  **unsigned** used-u16 at4 and payload at6. It follows links until zero and
  permits zero-used nodes. The explicit little-endian interpretation remains an
  admitted-format hypothesis, not portable equivalence to native casts.
- The same readers warn on descriptor-length disagreements. Our rejection of
  **every exact stored-length mismatch** is a stricter local admission policy.
  Likewise, selected-chain overlap is `UnsupportedSharing`, a conservative local
  restriction, not proof that every native database forbids sharing.
- [TableFiles.cpp:86–133](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableFiles.cpp#L86-L133),
  blob `2bf5d5f02bab1a7c0925af6193c16f2159da0eb8`, separately groups selected
  names and assigns addresses by part number. That later operation is not done.
- [ConfigStorage.cpp:258–332](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L258-L332),
  blob `3ec4e3ed0101b8a792a162c3111547af28de45b2`, concatenates stored parts
  before optional inflation. [352–375](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/ConfigStorage.cpp#L352-L375)
  classifies packedness using names/extensions. Therefore the bytes here are
  **stored bytes**, not universally compressed/plain/decompressed bytes or
  DATASIZE. Dynamic updates and applied-state selection remain outside scope.

## One attempt, two phases

`ConfigBlobChainProfile` preserves the exact seven declarations, string
recordlock0, integer format0, stride301 and ASCII-case CONFIG selection without
fallback. There is exactly one `CatalogReader`, selected table, opened data
mapping, opened BLOB mapping and cumulative budget graph. The public prerequisite
observer is never called and nothing is reopened under fresh budgets.

**Phase A** completes the entire prerequisite scan first: first-marker-one with
opaque reserved payload, all256 later marker classifications, strict structural
UTF-16LE validation of every zero-marker name, source-derived reference/name
exclusions, u32LE positive reference capacity bounds, canonical PARTNO0..4095 and
at least one selected part-zero witness. All nonzero-marker payloads and excluded
PARTNO remain unread. No grouping, matching or normalization of names occurs.
Only private `(start, stored_length, part_is_zero)` triples are retained, up to4095;
192 representation-weight bytes are reserved before each append. A bad final
prerequisite prevents **all** chain-block reads.

**Phase B** reads every selected chain, with only one private assembly at a time.
For logical block `i`, with `B = blob_logical_bytes // 256`:

1. Require exact integer `1 <= i < B`; charge the hop and shared work budgets.
2. Detect current-chain cycles, then previously selected-chain ownership.
   Reserve both visited and owner entries before insertion.
3. Read exactly six header bytes; decode u32LE next and u16LE used. Require
   `used <= 250` and next0 or `1 <= next < B`.
4. Reject `used > declared_length - written` **before** that payload callback.
   Read exactly used bytes at offset6, with no callback for used0, no unused
   padding and no full-block read. Copy into the pre-reserved fixed assembly.
5. Follow next even after written reaches the descriptor length. Zero-used
   intermediate/terminal tails are admitted but bounded by independent hop
   limits. No full-nonterminal-block or positive-every-block rule is invented.
6. Finish only at next0, and require exact descriptor length. No truncation,
   padding, guessed early termination, cache/deduplication or retries occur.

Any later chain failure invalidates the whole observation. Failure poisons the
private primitive; its charges and ownership are not refunded. Ownership uses a
**table-BLOB-local** logical-block namespace, distinct from root-catalog logical
blocks. Distinct blocks on one physical page are valid, while the unchanged
physical mapping role graph prevents conflicting physical ownership. Block0,
unselected/unreferenced blocks and allocator/free chains remain opaque. The
borrowed source is never closed or written.

The private primitive returns exact bytes for later internal consumers; the
public observation never returns them. No hash, callback sink or decompressor
consumes those bytes. Duplicate filenames/PARTNO and noncontiguous parts remain
unidentified; no file completeness or identity is inferred.

## Conjunctive resource policy

All four chain limits can be lowered, never raised:

| Dimension | Ceiling |
|---|---:|
| One declared stored chain length |1MiB|
| Cumulative selected declared lengths |4MiB|
| Hops per chain, including used0 |8192|
| Cumulative hops / logical owner entries |32768|

These limits **intersect remaining shared budgets**, not add a second allowance.
Catalog, descriptor, mappings and the full entry scan have already consumed
capacity when the first chain begins. The new observer rejects any caller-supplied
`CatalogLimits` field above its existing default. In particular, defaults stay
100000 page reads,64MiB read bytes,128MiB processed bytes,100000 BLOB visits,
16MiB total BLOB bytes,262144 mapping pages and32MiB output weight. All remaining
defaults are frozen in the recipe too. The64MiB image ceiling is unchanged.

Each declared length is charged once to both the cumulative chain-byte budget
and shared `total_blob_bytes`, with `2*length` representation weight reserved for
assembly and immutable returned bytes before either allocation. Copying work is
charged cumulatively. Each hop also charges shared `blob_visits`; each visited
and owner insertion reserves128 weight bytes. Header/payload range reads reserve
`3*n` weight for callback/assembly/final representations before reads; fixed
scalar temporaries and bounded container overhead receive separate reservations.
The same physical source charges every page touch, including repeat-page reads,
read bytes and processing work. No private callback bypass exists.

Discarding an assembly or visited set never refunds a cumulative charge. These
weights are conservative representation accounting, not an assertion about exact
Python allocator overhead. There is deliberately **no promise that all independent
maxima fit simultaneously** under shared budgets. Lowered shared limits reject
otherwise-valid chains rather than reset, remap, widen or retry them.

The frozen recipe is `config_blob_chain_8380_8192_v1`, SHA256
`e4d826310b61731e380156aaf2dc81e1a1bb342212f5a5f7596b30a51f1e6137`.

## Closed finite observation

The inherited structural/selection summary is retained, plus only:

- `completed_chain_count` K;
- `total_stored_bytes_read` D;
- `total_chain_blocks` H;
- `maximum_chain_hops` M;
- `multi_block_chain_count` Q;
- `zero_payload_block_count` Z.

The independent policy requires exact primitives (Boolean is not integer), all
inherited partitions, a positive selected part-zero witness, and:

- `K = selected_reference_count >= 1`;
- `K <= H <= min(32768, B-1)` and `1 <= M <= min(8192,H)`;
- `0 <= Q <= K`; if Q0, H=K and M1;
- if Q>0, M>=2 and `K+Q+M-2 <= H <= (K-Q)+Q*M`;
- `0 <= Z <= H-K` and `H-Z <= D <= min(4MiB,K*1MiB,250*(H-Z))`, D>=K;
- selected data+BLOB logical lengths fit the same bound postimage.

The actual private assembly and per-chain byte cap are **source-bound producer
facts**; aggregate counters alone cannot independently reconstruct them. A
successful native result with Q0 witnesses no nonzero-link traversal in that
image: such traversal then has synthetic coverage only. No fixed native count,
payload size, multiblock count or filename expectation is introduced.

Fixed classes distinguish transport from content:
`chain_validation=selected_zero_terminated_exact_stored_length`,
`transport_validation=all_selected_stored_bytes_read`,
`compression_validation=not_classified`. Framing remains `not_accepted`;
root/file identity and applied state remain `not_observed`. Extraction,
decompression, mapping and layout remain `not_run`; native byte equivalence is
`not_observed` and compatibility is `not_claimed`. Stored bytes read do not mean
payload semantics are valid. No names/name hashes, positions, pointers,
per-reference lengths/parts, block lists, raw payloads/payload hashes or arbitrary
exception text escape.

## Explicit lane, finite envelope and unchanged lifecycle

```sh
python3 scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --config-blob-chain-observation --output native-db-oracle/report.json
```

The explicit lane is `owned_config_blob_chain_v1`, report15/capture16/invocation12.
Its inventory is exactly23 producer sources: the existing21 metadata sources,
common CONFIG reader and one replacement policy. No broad named-file/PARAMS
extraction module is staged. All prior lanes remain separately selectable.

The workflow changes only the selector. Image, admission/security, artifacts,
13 stages,11 snapshots, five comparisons and four cleanup gates remain unchanged.
There is no new native command, clone or lifecycle phase. The existing baseline
observer reads the owned auditor's closed post-session frozen image; any later
failure discards the earlier observation.

Caps remain projection2048/capture12288/report32768. The independently constructed
rectangular projection envelope is1258 bytes, even charging integer widths whose
maxima cannot coexist. Capture using the full projection cap is2988 bytes. The
**whole report**, all source paths, lifecycle fields, full capture cap and final
newline total31410 bytes, leaving1358. Bounds are frozen before any native run;
no capture is used to discover whether output fits or to widen a cap.

## Verification and native gate

```sh
python -m unittest discover -s tests -p 'test_native_1c_db_oracle_config_blob_chain*.py' -v
```

Synthetic coverage includes exact private byte equality, arbitrary/nonmonotonic
links, page31→32 with shuffled physical backing, partial/full blocks, zero-used
tails, used251/65535, wrong endian, invalid bounds, inexact reads, early zero,
excess rejected before payload read, cycles after reached length, duplicate starts
and shared suffixes, distinct same-page blocks, final prerequisite/chain failures,
all4095 selected entries, hard and lowered chain-byte/hop boundaries, independently
lowered shared budgets and reservation-before-allocation/read/insertion checks.
Closed-policy tests cover conservation/types/classes, prohibited exports,
recipe/source/image/nonce/origin/postimage substitution, every prior lane and all
late cleanup gates. Actual23-source cold staging validates core output and the
production final report validator without the interpreter or unstaged modules.

Fresh native acceptance remains a separate gate: independently bind exact
published head/tree and ordered execution graph, all23 source pins, frozen
recipe/invocation/executed command, genuine ordered jobs, hardened sole report
ZIP, exact report bytes, production final validator, closed postimage and all
four cleanup gates. Reuse no native image or old acceptance. Green CI alone does
not supply native transport evidence. A failed hypothesis remains failed and must
not be broadened after seeing its capture.

The next coherent consumer is explicitly bounded part/file assembly and
compression classification. Container/root/applied-state interpretation requires
its own source-grounded design and evidence, not another claim from these counts.
