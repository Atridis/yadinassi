# Experimental bounded DBNames identities

This independent slice parses a narrow PARAMS/DBNames content profile and prepares
an explicitly selected owned-fixture UUID/name comparison. Local synthetic tests
are not native content evidence. No native result for this new lane is claimed.
Existing extraction evidence establishes transport only, not content or mapping.

## One exact content hypothesis

`parse_dbnames(data, *, profile, limits)` in `filedb_dbnames.py` is standalone
standard-library code. It receives decompressed immutable bytes, never fixture
identities, expected names, a catalog, a path or a native API. The explicit
`DBNamesParseProfile` selects only `dbnames_utf8bom_counted_triples_v1`:

- UTF-8 BOM is mandatory. No alternative encoding or missing-BOM fallback.
- One complete root has form `{H,{N,{UUID,"Kind",ID},...}}`, with ASCII
  space/tab/CR/LF between tokens and only such whitespace after the root.
- H is a retained, semantically opaque unsigned header integer. It is not a
  validated format version, count or maximum ID. No H-to-ID relation is assumed.
- N must equal the actual complete number of three-scalar entries. There are no
  extra root children, nested entries, trailing commas, missing entries or tails.
- UUID is a bare 8-4-4-4-12 hexadecimal token; kind is a quoted ASCII identifier
  `[A-Za-z][A-Za-z0-9_]{0,31}`; ID is a canonical unsigned decimal integer.
- H and ID are 0..2147483647. Only positive IDs can be mapped. Zero UUIDs,
  unsupported kinds and duplicates are retained in order, not silently dropped.
  Only Reference/Fld are considered by the owned comparator.

Frozen output retains original lexical spellings, canonical UUID identity,
integer ID and source ordinal. Ambiguous targets are rejected by comparison,
never resolved by first match. This is not a general metadata AST or serializer.

Initial defaults are also hard ceilings: 8 MiB input, 4096 entries, 65536 tokens,
depth 4, 128 encoded bytes per scalar, 10 decimal digits and 16 MiB cumulative
representation accounting. Limits can be lowered, not widened. UTF-8 validation
and scanning do not allocate a complete decoded copy. The reservation helper
uses actual admitted byte length and the shortest legal entry encoding to bound
retained representation/work before construction. It does not reserve the full
16 MiB ceiling for every input or claim exact Python heap usage.

## Same-reader extraction and independent comparison

The public `read_dbnames` signature and result semantics are unchanged. A private
same-reader seam accepts only the identical completed physical catalog. Fixed
PARAMS selection, data/BLOB ownership and cumulative catalog budgets remain on
one CatalogReader. Its extraction attempt is single-use, even after failure.
The identity adapter reserves parser/comparison work on that same budget. It
neither rescans the catalog nor resets/refunds budgets.

`--dbnames-identity-validation` is separate from all older modes. The lane is
`owned_dbnames_identity_validation_v1`, report schema 9, capture schema 10 and
invocation schema 6. Its exact 26-source inventory is the extraction inventory
plus the pure parser and separate identity policy. Older 18/20/21/22/23/24 source
memberships and validators remain closed. The identity lane remains explicitly selectable. The reviewed CI workflow now
selects the separate [zero-marker CONFIG filename-field observation](config-zero-marker-filename-observation.md),
not identity validation; the default CLI behavior remains unchanged.

Three expected UUIDs are generated owned-fixture metadata, independently read
from catalog/Payload/Amount XML after the existing successful post-apply native
redump and reverified at the existing baseline-observer redump. Their exact paths
and canonical source binding are retained through the source-pinned, read-only
baseline metadata audit. No additional native call is introduced. This does not
prove that arbitrary editable CONFIGSAVE describes applied CONFIG.

DBNames parsing completes before XML/native expectations reach the comparator.
The comparator requires a unique UUID/kind target for each of the three roles,
then joins native rows by exact logical plus metadata path. It independently
constructs full native names `_Reference{n}` / `_Fld{n}` and full physical names
`_Reference{n}` / `_FLD{n}`. Each is compared exactly against its own channel, with
physical uniqueness and field containment. Historical native/physical casing
actually differs for fields; the raw values are not normalized or declared equal.
No suffix search, proximity, row-order or expected-number-driven parsing occurs.

Only three owned-role rows can be public: expected/parsed UUID, original UUID,
kind/ID/ordinal, predicted/native and predicted/physical names and equality facts.
Other entries and payloads remain private. Finite header/count summaries and
profile/transport digests accompany complete source/image/nonce/XML/frozen-image
bindings. Proposed caps remain 6144-byte combined projection, 12288-byte capture
and 32768-byte whole report including its newline; complete serialized envelopes
must be tested independently before execution.

A successful future verdict is only `owned_identity_names_matched`. Native byte
equivalence remains `not_observed`, general native compatibility `not_claimed`,
and record/layout acceptance not run. All existing 13 stages, 11 snapshots,
5 paired comparisons and 4 cleanup gates remain mandatory. A later failure
invalidates the successful capture.

## Source basis and limits

The strict count/three-field hypothesis is informed by independent primary
implementations, not an official platform specification:

- [DaJet count and positional facts](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/DbNamesParser.cs),
  blob `d30b14e0914a54a9dba6726dfc693849495b06f4`.
- [DaJet-metadata lexical positions](https://github.com/zhichkin/dajet-metadata/blob/3058bb4c5b92e70afa299d9f106f2ef9cfeded07/src/dajet-metadata/loader/DBNames.cs),
  blob `7bfa0d43c78f75ea42a9ad5b67387633a28da9a2`.
- [UTF-8 BOM handling](https://github.com/zhichkin/dajet-metadata/blob/3058bb4c5b92e70afa299d9f106f2ef9cfeded07/src/dajet-metadata/parser/ConfigFileReader.cs),
  blob `39d96b68c16522a88178555a65b0e44adb62a044`.
- [Tool1CD entry order and table-name observations](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Class_1CD.cpp#L1518-L1615),
  blob `9fd03be99ddb0de9c8274a6206fff6e4ebef2f58`.

No upstream implementation was copied, translated or executed. Full root/count
conservation and EOF are deliberately stricter than these consumers. Unknown
schema fails the one hypothesis, not a fallback search. A fresh owned run must
still establish the limited XML/Fld correspondence. CONFIG/CONFIGSAVE resolution,
CF/DT, general metadata trees, second independent configurations, logical record
access and BSL database managers remain outside this slice.
