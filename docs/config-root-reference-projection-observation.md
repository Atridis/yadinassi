# Partial CONFIG root-reference observation

This explicit experimental lane integrates the
[bounded prefix projector](config-root-prefix-projection.md) into the existing
[single-part CONFIG content reader](config-content-decode-observation.md).
It asks only whether a selected `root` entry supplies a bounded candidate GUID
prefix and that name resolves to one completely decoded positive entry in the
**same CONFIG table and the same owned reader graph**.

It does not validate the complete root document, unknown suffix, target content
semantics, metadata identity, applied configuration, or native byte equivalence.
All current evidence is synthetic. The lane has not been executed against a
native file database; `native_acceptance` remains `pending`. Earlier closed
full-root and failure-diagnostic experiments are not reopened or reclassified.

## Source evidence and limits of the hypothesis

At DaJet commit `6af0c0baab11f9d281ad42a3eb2269d5b113cde5`,
[RootFileParser.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/RootFileParser.cs)
reads child position 1 as a GUID and cancels parsing.
[OneDbMetadataProvider.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/OneDbMetadataProvider.cs#L667-L679)
reads CONFIG/root, then
[uses that projected GUID as a CONFIG name](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/OneDbMetadataProvider.cs#L714-L718).
Its reader is SQL Server/PostgreSQL-backed, not a physical `.1CD` reader. These
facts motivate a positional projection hypothesis, not a native file-format
specification. No upstream implementation is copied, translated or executed.

The projector's explicit BOM/unsigned-header/bare-GUID/delimiter profile is
unchanged. The header is uninterpreted, not assumed to be a count or version.
A comma or closing brace ends the prefix; every following byte remains unread by
the projector, even invalid UTF-8, garbage or unfinished syntax. Successful
projection is never substituted for complete-document validation.

The content reader's exact stored length, no sharing, ASCII-only names,
part-zero-only admission, raw-DEFLATE full-consumption and positive target
requirements are deliberately conservative local policies. Failure does not
establish that a native database is corrupt or unsupported in every other mode.

## One private resource graph

1. One `CatalogReader` selects the sole CONFIG table and opens its data and BLOB
   mappings. All previous profile/marker/name/locator/PARTNO guards run first.
   Every selected name must be printable ASCII, uniquely ASCII-folded, non-dynamic
   and part zero. Excluded rows and nonzero-marker payloads retain their previous
   interpretation; this is not a census of every possible native file.
2. A bounded private folded-name map retains each selected chain reference and
   compression class. Names are not trimmed, normalized or treated as paths.
   Exactly the selected folded key `root` must be present.
3. One chain primitive and one decoder share the original reader's cumulative
   budget. The root entry is completely decoded once. The prefix projector's
   work/output reservation is charged against this identical budget before
   parsing. No expected UUID or native count is supplied.
4. The normalized candidate GUID must resolve to a selected key in that same
   map. That target's exact chain and complete content are decoded once; decoded
   content must be positive. Zero GUID is not rejected by invented semantics:
   it succeeds only if the same-table entry actually exists and passes the guards.
5. Every remaining selected chain/content pair is decoded exactly once before
   return. A malformed unrelated entry, alias/overlap, exhausted allowance or
   final output reservation invalidates the entire observation. There is no
   partial success, second reader, reread, fallback, refund or retry.

Root and target may appear anywhere in physical record order. The fixed execution
order is root, target, then all remaining selected entries in scan order. This
order makes target content independent of an arbitrary file ordering without
retaining all decoded content simultaneously. Original names, GUID spellings,
root and target bytes, offsets, payload hashes and pointers never enter the
returned observation or report.

The existing content observer is byte-for-byte unchanged. The new observer
repeats its bounded framing scan but uses the same low-level primitives; this
intentional duplication avoids changing historically pinned observer behavior
merely to deduplicate code. Tests pin the complete previous source prefix with
checkout newline normalization.

## Resources and finite result

All existing image, catalog, chain, content and inflate-call ceilings remain
unchanged and lowerable only. Extra retained map storage is charged before
allocation at `256 + 4*name_units` output weight and `name_units` work per selected
entry, in addition to the existing classification charges. A fixed 256 output
weight precedes projector profile/limit/reservation construction; the projector
then reserves 2048 output weight and `4*min(input_length,1024)+2048` work before
parsing. These are conservative representation/work units, not exact Python
heap or CPU measurements. Removing objects never refunds charges.

In addition to the old aggregate counters, success exposes only three exact
integer-one counters: projected roots, resolved candidate targets and positive
targets. Fixed status strings state `partial_prefix_candidate_same_table`,
`root_document_validation=not_performed`, and
`root_suffix_validation=not_performed`. Root identity, file identity and applied
state remain `not_observed`; native compatibility remains `not_claimed`.
Both root and GUID-name target fall under raw DEFLATE in the frozen name rule,
so a successful summary requires at least two selected/positive packed entries
and at least 44 total inflated bytes (shortest root prefix 43 plus positive
target). Counters do not replace the source-bound producer's actual checks.

Errors are finite category/code pairs. No offending GUID, name, byte or exception
text is exported. All four cleanup gates remain mandatory; a later lifecycle or
cleanup failure discards the observation.

## Explicit route and source binding

The new, mutually exclusive selector is:

```
python scripts/native_1c_db_oracle.py --execute-approved-image --file-db-oracle --config-root-reference-projection-observation --output native-db-oracle/report.json
```

The workflow changes only its existing reviewed command's selector from
`--config-content-decode-observation` to this explicit partial-reference lane.
Admission, credentials, image, network isolation, limits and cleanup are
unchanged. Publishing this change to an ordinary PR branch does not execute the
dedicated workflow; its trigger remains the separately approved normal advance
of the exact reviewed-runner branch. No dedicated run has yet been performed.

- Lane: `owned_config_root_reference_projection_v1`
- Report / capture / invocation schemas: 23 / 24 / 16 (not reused historical IDs)
- Recipe: `config_root_reference_projection_8380_8192_v1`
- Recipe SHA-256: `839bf2937921e5880cf25ff079b17f735d71b34fa06b3ffdb8ba344748a19694`
- Exactly 24 staged sources: the existing 21 metadata sources, common framing
  reader, this lane's closed policy, and the stdlib-only prefix projector.
- Old inventories stay unchanged. The staged lane cannot import the interpreter
  or silently select a different policy. Missing, modified or extra source files
  are rejected before execution.

The rectangular serializer proof includes every source path/hash, stage,
snapshot, comparison, artifact, failure context, cleanup flag and final newline:

- Projection envelope: 1709 bytes of the unchanged 2048-byte cap.
- Capture with full projection cap: 3003 bytes of the unchanged 12288-byte cap.
- Full report with full capture cap and newline: 31631 bytes of the unchanged
  32768-byte cap, leaving 1137 bytes.

No global 512-source majorant, 8192-byte wire limit or 32768-byte report limit is
raised to accommodate this lane.

## Verification and native gate

Focused tests cover all-selected admission, exact-once same-reader ordering,
missing/duplicate root/target, case folding without trimming, arbitrary suffixes,
zero GUID, aliases/overlap, malformed target and unrelated later chains/streams,
empty target, exact and one-less resource limits, exact projector charge ordering,
poisoned failure contexts, cold flat imports, physical postimage binding,
finite report mutations and all four cleanup gates.

A future native observation must bind the actual reviewed commit/tree, all 24
source hashes, recipe, approved image and native identity, executed command/jobs,
sole hardened report archive, production final validator, finite counters and
cleanup. Only then may this narrow **partial-reference observation** be described
as witnessed on that exact file database. It still will not validate the unknown
root suffix, target metadata, applied configuration or native byte equivalence.
No failed hypothesis is grounds to widen grammar or budgets automatically.
