# Experimental private CONFIG Catalog attributes

`project_catalog_attributes(data, *, budget, limits=None)` is an opt-in Python
projection of one **already selected, decoded Catalog payload**. It is not a
file selector, a native fixture verdict, or an end-to-end Catalog reader.
Only synthetic tests currently establish this new API's behavior. No previous
native run is relabeled as evidence for it.

## Independent input and useful output

The inputs are immutable bytes, the caller's existing cumulative storage budget,
and optional lower limits. Expected UUIDs, XML, native metadata, DBNames IDs,
physical declarations and row values are not inputs. No file or network access
occurs. The frozen result preserves collection order and contains each attribute's
UUID, Name, type token and qualifier tuple:

- `S`: `(length, StringKind)`;
- `N`: `(precision, scale, NumericKind)`.

Lengths and numeric precision/scale come from CONFIG. They are not fixed to the
owned Payload(32)/Amount(9,2) examples. Invented tests include length 7/456,
precision 17 and scale 5. These are parser preservation tests, not native range
or storage-codec evidence. Standard Catalog CodeLength and DescriptionLength
remain the responsibility of the separate existing identity/standard API.

This supplies the missing attribute identities/types for a future join:
Catalog identity → attribute identities → DBNames → physical fields → values.
That join is **not implemented here**. In particular, no XML identities are
substituted for parsed attributes, and no existing fixed-layout row profile is
silently generalized.

## Pinned executable positional evidence

The source basis is DaJet commit
`6af0c0baab11f9d281ad42a3eb2269d5b113cde5`, not an official platform specification:

1. [CatalogParser](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/CatalogParser.cs)
   registers the attribute collection callback at `[6]` and delegates to the
   property collection parser. Blob `67d3a6a23973301317c7d160e1adc35c41983e51`.
2. [MetadataPropertyCollectionParser](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/MetadataPropertyCollectionParser.cs)
   reads collection UUID at `[0]`, count at `[1]`, and entries at `[2+n]`.
   Relative to each entry, executable converters register UUID at
   `[0][1][1][1][1][2]`, Name at `[0][1][1][1][2]`, and type at `[0][1][1][2]`.
   The type callback invokes the descriptor parser.
   Blob `5bbfc259ed4a88eb3e0f3bcdad5d3cb1e92853bf`.
3. [DataTypeDescriptorParser](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/DataTypeDescriptorParser.cs)
   checks the Pattern marker, dispatches S/N primitives, then assigns string
   length/kind or numeric precision/scale/kind from their qualifier positions.
   Blob `09689e4c8e08c4e7befdd64b7d910db830fd2463`.
4. [SystemUuid](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/core/constants/SystemUuid.cs)
   declares the Catalog attribute collection UUID
   `cf4abea7-37b2-11d4-940f-008048da11f9`.
   Blob `26598de61d6eab63c0a19aae70a6c03fbafad6d3`.
5. [StringKind](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/model/enums/StringLength.cs)
   defines fixed=0, variable=1; [NumericKind](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/model/enums/NumericKind.cs)
   defines signed=0, unsigned=1. Their blobs are respectively
   `547dd5c02d96ca487f1aac30240970a29b472fb0` and
   `fb4894c74be6af83bfba9f7b1d908c749e659014`.

These are executable registration/assignment facts, not inferred offsets from
comments. No upstream implementation is copied, translated or executed. The
local iterative selective walk reuses this project's bounded Unicode/token
scanner and UUID grammar; it constructs no complete AST.

## Deliberately narrower admission

The `[6]` collection must close with exactly its declared count plus the two
header fields. UUIDs use bare canonical-shape hex/hyphens, normalize to lowercase,
and must be nonzero. Duplicate canonical UUIDs or exact Name spellings reject the
whole result. Case-folded/locale-equivalent names are not resolved or certified.
Names must be nonempty quoted strings. Every required ancestor must be an object.

Only `{"Pattern",{"S",length,kind}}` or
`{"Pattern",{"N",precision,scale,kind}}` is admitted. The fixed Pattern marker
and S/N tokens are quoted. Qualifiers are canonical bare nonnegative ASCII
integers, bounded by 2147483647; kind is 0 or 1. Numeric precision must be positive
and scale cannot exceed precision. These are local admission rules, not the
platform's valid property ranges. String length zero is retained as metadata,
not accepted as a supported physical storage layout.

DaJet also accepts a qualifier-less `{"S"}` descriptor; this profile explicitly
does **not**. Composite, Boolean, Date, reference, unspecified and unknown types
are unsupported. There is no fallback search, inferred default or dropped
unknown attribute. Extension resolution, property usage and other attribute
properties are not interpreted.

The walker validates the traversed syntax through the complete collection and
requires a real parent comma/close boundary. It stops there: the remaining Catalog
suffix and the enclosing whole document are not validated. This API does not
establish that the payload is an applied Catalog or bind it to an external key.

## Budgets and failure behavior

Hard ceilings: 4 MiB input, 131072 tokens, depth 64, 64 attributes, 1024 UTF-8
bytes/256 characters per Name. Caller limits can only decrease. Attribute count
and fixed Pattern parsing do not accidentally consume a lower field-value/name
limit. The shared budget can impose stricter cumulative limits.

Before cursor/output construction, the API charges `8 * input_length` processing
units and 262144 representation bytes, then charges token visits as it walks.
The reservation covers bounded names/UUIDs, output/temporary records, sets and
depth-bounded paths/frames; it is admission accounting, not exact Python heap RSS.
Opaque scalar values are scanned without retention. No budget reset/refund or
per-attribute allowance exists. Failure publishes no partial result and retains
all successful charges; a caller must discard a failed wider read operation.
Diagnostics contain finite codes only, never raw metadata or names.

Focused tests cover independent invented bytes, changed names/UUIDs/lengths,
count and path corruption, unsupported types, duplicates, every truncation,
Unicode, lowered/cumulative budgets, maximum count, immutable results, and
isolated `python -I -S -B` import without the interpreter. Existing CONFIG APIs,
older oracle lane contracts, rights, fixtures and record codecs remain unchanged.

## Separate dedicated native binding route (acceptance pending)

`--config-catalog-attribute-binding` alone selects invocation 22, report 35,
capture 36 and `owned_config_catalog_attribute_binding_v1`. It stages exactly
28 files: the old matrix inventory with its policy replaced by the attribute
policy, plus the new runtime parser. Older inventories do not acquire this
parser. The workflow changes exactly one selector token from the matrix lane to this
route; image, permissions, admission checks and cleanup remain unchanged.
That activation alone is not native acceptance.

The unchanged matrix fixture contains three Catalogs: the original with Payload
and Amount, and two empty additional Catalogs. No extra rows, rights, BSL
operations or native lifecycle stages are added. The CONFIG reader uses one
CatalogReader/resource graph, decodes each selected payload once, then invokes
**two bounded parsers** on each Catalog's same bytes: identity and attributes.
Both processing reservations and every token visit accumulate on the original
budget. This is one database-read graph, not a claim of one grammar traversal.

The independently verified canonical native-redump XML manifest includes each
complete direct attribute collection: UUID, Name and type qualifiers. These XML
facts are checked only after byte parsing completes. Comparison requires an exact
UUID bijection, including the empty collections; names/types/qualifiers must
match. Attribute order is not used as logical identity. No hardcoded Payload
length or Amount precision is passed to the parser or used as a substitute for
XML values. Fixed counts of three Catalogs and two attributes are only admission
rules of this owned fixture lane.

Private names, UUIDs and qualifiers never enter public reports. The projection
adds only `attribute_count=2` and a finite identity/fields/attributes verdict.
Source, recipe, manifest and frozen-image hashes remain bound. The unchanged
13-stage/11-snapshot/5-comparison lifecycle and four cleanup gates are required;
subsequent failure discards the success. Native execution and acceptance are
still pending, and older identity/matrix runs cannot establish this new claim.

Independent complete-envelope tests charge maximum counters, all staged source
paths, optional failure context, the entire capture allowance and final newline:

| Envelope | Maximum bytes | Unchanged cap |
| --- | ---: | ---: |
| Projection | 2033 | 2048 |
| Capture with full projection allowance | 3097 | 12288 |
| Report with full capture allowance | 32094 | 32768 |

The report includes all 13 stages, 11 snapshots, 5 comparisons, 3 artifacts and
4 cleanup gates. Separate ordinary runtime provenance now counts 72 source files;
its new digest requires fresh runtime validation. No guard/cap is increased.

A source-bound run still needs a cold production FINAL check followed by the
independently frozen checker. Until that run is audited, native attribute
projection remains unverified. BSL `Метаданные`, `Справочники`, references,
queries, general CRUD and live database access remain unsupported.
