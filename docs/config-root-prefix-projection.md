# Experimental partial CONFIG/root reference projection

This is a standalone lexical utility, not a new native observation lane or a
complete CONFIG/root parser. It has synthetic coverage only. No production
reader, workflow, reviewed-runner branch, source-staging policy, report envelope,
or acceptance decision calls it. The closed #122/#124 experiments remain closed;
their failed complete-document hypothesis is not reclassified as successful.

## Why a separate projection

At DaJet commit `6af0c0baab11f9d281ad42a3eb2269d5b113cde5`:

- [RootFileParser.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/RootFileParser.cs)
  registers a handler for child position 1, reads a GUID, then cancels parsing.
- [ConfigFileParser.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/ConfigFileParser.cs)
  stops when that handler requests cancellation.
- [OneDbMetadataProvider.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/OneDbMetadataProvider.cs#L667-L679)
  reads `CONFIG/root`, then [uses the projected GUID as a CONFIG filename](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/OneDbMetadataProvider.cs#L714-L718).
- [ConfigFileReader.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/ConfigFileReader.cs)
  is a SQL Server/PostgreSQL reader here, **not a physical .1CD reader**. Its
  lexical and GUID handling is broader and may return an empty GUID for invalid
  input. This implementation does not copy that permissive failure behavior.

These facts support investigating a positional prefix projection. They do not
specify the complete root grammar, the meaning of child zero, file-database
equivalence, a valid suffix, or the existence/identity of a target file.
Upstream code is neither copied nor executed. The grammar below is an original,
deliberately conservative local hypothesis, not a portable native specification.

## Explicit contract

The stdlib-only module `yadinassi.storage.config_root_projection` recognizes only
the named profile `config_root_bom_uint_bare_guid_prefix_v1`:

```
BOM WS { WS UINT WS , WS GUID WS ( , | } )
```

- BOM is exactly UTF-8 EF BB BF. WS is ASCII space, tab, CR, or LF.
- UINT is canonical unsigned decimal in 0..2147483647. It is retained without
  interpreting it as an arity, count, version, or validity flag. No expected
  first-field value is passed into the projector.
- GUID is exactly bare 8-4-4-4-12 hexadecimal text. Both original case and lowercase
  spelling are returned. Zero GUID is preserved as an uninterpreted value, not
  accepted as a meaningful target or rejected by an invented semantic rule.
- The byte after optional GUID-following whitespace must be comma or closing
  brace. It is consumed as the lexical boundary, then parsing stops immediately.

`RootReferencePrefixProjection` is immutable and explicitly partial. Its
`capability` is `partial_root_reference_prefix`; `document_validation` and
`suffix_validation` are always `not_performed`. It has no success/valid/native
acceptance Boolean. `prefix_end` is the first byte after the observed delimiter.
It does not promise there is another token or a complete object at that offset.
Native research state belongs in evidence/documentation, not a runtime result.

**Even a closing-brace delimiter does not validate the document.** Any following
bytes, including invalid UTF-8, garbage, unmatched braces, or a truncated token,
remain unread and unvalidated. Whole-document UTF-8, nesting, arity, EOF, tail
semantics, cryptographic authenticity, metadata identity, and applied-state
selection are outside this contract. A result must never substitute for a
complete-document acceptance check.

## Bounds and caller responsibilities

Input is exact immutable `bytes`; profiles and limits also require exact types.
Defaults are hard, lowerable ceilings:

- Input length: 4 MiB, matching `ConfigContentDecodeLimits.max_content_bytes` in
  `scripts/native_1c_db_oracle/config_framing_reader.py`, the current CONFIG content
  decoder's per-entry ceiling (not the separate PARAMS/DBNames transport limit).
  This check uses length only; it does not scan the full content.
- Inspected prefix: 1024 bytes, including BOM, whitespace, and delimiter. This is
  a conservative local policy, not a claim about native maximum root length.
- Cumulative output representation weight: 2048 bytes. Four possible prefix
  passes plus that weight bound reserved work; no full-input copy, suffix copy,
  token vector, recursive parser, or general syntax tree is allocated.

The fixed output weight covers the result, reservation, cursor, bounded integers,
the two GUID spellings and raw header (at most 82 retained ASCII characters),
and transient bounded copies. Weights are conservative accounting units, not
an exact Python heap or CPU bound. `reserve_root_projection` is O(1), before any
input-derived allocation. A future shared-budget caller must charge the returned
work/output weights before parsing the identical immutable bytes/profile/limits,
without budget reset or refund. The supplied input has separate caller ownership.
All errors have a finite code and never include source values.

The prospective caller is a separately reviewed experimental CONFIG consumer
that already obtained privately decoded bytes through one same-reader resource
graph. This increment deliberately does **not** connect that caller. Target
lookup, same-table uniqueness, complete target transport, native source binding,
closed diagnostics, and any actual file-database observation require a subsequent
explicit contract and genuine native evidence. No reference or suffix is exported
by the current oracle because it does not call this utility.

## Rejected alternatives

- Requiring EOF immediately after `{2,GUID}` repeats the unsupported complete-root
  hypothesis rather than answering a partial-projection question.
- Searching arbitrary bytes for a UUID would lose structural position and permit
  suffix/embedded values to become false references.
- Silently relaxing an existing complete parser would change its security and
  evidence contract. This new type and function cannot serve as that fallback.
- Parsing or guessing the unknown tail, selecting the first matching target,
  following CONFIGSAVE overlays, or declaring applied state adds unsupported
  semantics and is not part of this increment.
- Returning a successful projection as native acceptance confuses a bounded
  lexical observation with file-database behavior. Synthetic tests are not native
  evidence, and the SQL-based upstream usage does not close that gap.

## Local verification

```
python -m unittest discover -s tests -p test_config_root_projection.py -v
```

Tests cover exact primitive/profile checks, header/GUID boundaries, every prefix
truncation, all GUID-byte invalid substitutions, whitespace placement, lowered
and exact prefix/input/output limits, frozen results, finite errors, and deliberate
suffix nonvalidation. No existing native fixture, database, external process,
or network service is involved.
