# Experimental partial Catalog Name projection

`yadinassi.storage.config_catalog_name.project_catalog_name_prefix(data, *,
budget, limits=None)` is a pure local candidate. It returns an immutable private
`CatalogNamePrefix(name)` from the zero-based positional path `[1][9][1][2]` in
already-decoded Catalog bytes. It takes no expected name, UUID, declaration key,
path, file reader, or platform API. It has no native evidence yet. The explicit oracle lane below uses this parser;
it is not connected to the Interpreter or ordinary BSL CLI.

## Meaning and non-claims

This is a candidate scalar name, not a validated BSL identifier, logical object,
reference type, or whole configuration. The caller may independently associate
the result with a previously resolved declaration key; this function does not
return, infer, or validate an embedded UUID. A later comparison may bind that
external key and parsed name to independently verified owned-fixture XML. The explicit owned-fixture lane below implements that separate comparison.

Only the required prefix and structurally skipped preceding positions are
validated. After the name's real comma/close-brace delimiter is established,
processing stops without consuming that delimiter or reading beyond it. The
remaining bytes, enclosing closes and EOF are not validated; an invalid UTF-8
suffix is deliberately outside the claim. A partial result never means the
whole Catalog document is well formed. Other scalar values are skipped without
retaining their contents. There is no content search or first-name match.

Visited bytes are strict UTF-8. One initial BOM is allowed; embedded BOM,
surrogates, overlong encodings, DEL and C0 controls other than CR/LF are rejected.
Boundary whitespace is SP/CR/LF. Positional nulls are retained, so `{}` has one
null child and `{,}` has two. Names must be nonempty bare or quoted scalars;
doubled quotes are decoded and quoting delimiters are inert. Name control
characters are rejected, including CR/LF. Strings are not normalized, trimmed,
casefolded or checked against expected values. In particular, a trailing space
in a started bare scalar remains part of its candidate name. Acceptance of a
synthetic spelling does not prove that the platform admits it as a Catalog name.

## Independent source basis

The only format-specific positional fact comes from pinned
[DaJet CatalogParser.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/CatalogParser.cs),
blob `67d3a6a23973301317c7d160e1adc35c41983e51`: its executable Name callback is
registered at `[1][9][1][2]`. Its metadata UUID comes from the caller's
file/declaration key. A different embedded-UUID path appears only in a comment;
this implementation makes no claim about it. The zero-based position model was
checked against the same revision's `ConfigFileReader.cs` and
`ConfigFileParser.cs`. This is independent primary implementation evidence, not
an official platform format specification or native verification of this code.
No upstream source is copied, translated, adapted or executed.

## Cumulative resource accounting

Hard ceilings, lowerable only: 4 MiB input, 131072 events, depth64, 1024 encoded
bytes and256 Unicode code points in the selected name. Effective depth also
intersects the caller's existing `max_tree_depth`. No complete decoded string,
DOM or per-event path history is constructed. At most64 small frames and256
name characters are retained; skipped scalar text has constant storage.

Before cursor, traversal stack or name buffers exist, the same caller budget is
charged `4 * len(input)` processing units and65536 representation bytes. The
fixed representation weight conservatively covers cursor state, bounded frames,
character list and result construction; it is not an exact Python VM RSS claim.
Every structural opening, closing and scalar/null event then charges the same
cumulative token counter before frame/scalar growth. Failed calls retain all
successful charges. No budget is reset, replaced or refunded. Native integration
must also account for existing decoding and all other candidates on that same
budget; repeated parser calls are not free.

The result and source bytes remain private. Exceptions have a closed finite
code set and never interpolate raw strings, offsets or names. The pure parser never serializes an observation. Its caller uses the finite
projection below without changing report/capture/output caps.

## Local validation and future native gate

`PYTHONPATH=tests python -m unittest test_config_catalog_name` exercises invented
positive/negative vectors, exact position/null semantics, UTF-8, quoted/bare
boundaries, unvalidated suffixes, limit edges, budget precharge, no refund, and
error privacy. These are synthetic tests only.

## Explicit owned declared-key/name binding lane

`--config-catalog-name-binding` selects invocation18, report27, capture28 and
`owned_config_catalog_name_binding_v1`. Its exact26-source inventory replaces
only the policy member and adds the name parser relative to the earlier25-file
Catalog-reference lane. All older inventories, selectors, schemas and recipes
remain unchanged. The checked-in reviewed-branch workflow now selects this new lane. Merely
opening a PR or pushing main does not run it; a separately reviewed exact-SHA
advance of the dedicated branch remains required. No native run is claimed here.

The new reader retains private `(declaration_key, parsed_name)` pairs while
validating all selected CONFIG entries on one reader, chain decoder and shared
budget. It reserves131072 representation bytes for bounded private pair
containers before growth; every name parser invocation charges its own65536
reservation, retained cumulatively. No file is reread or reinflated. A late
failure of any selected entry poisons the whole result, even after the name was
parsed. The owned route requires exactly one declared/resolved/positive object.

Only after completed parsing, a separate comparator receives the private
manifest produced after the existing native `verify_redump` call. Exact
namespace-qualified Catalog UUID and direct Properties/Name are read from the
expected and actual owned XML, with canonical whole-XML equality and complete
expected-source-tree stability. The seed manifest is reverified at baseline;
the readback route requires that verification before acquiring its auditor
clone. There are no new native commands, fixture objects, rights, credentials
or persistent access. Version2 and later mutations cannot silently replace the
version1 identity baseline.

The comparison checks the externally declared key against the XML Catalog UUID
and the independently parsed Name against XML Name. It does not inspect an
embedded UUID, reference-type UUID, other properties or arbitrary applied
CONFIG/CONFIGSAVE. Public success contains only a finite name count, the label
`owned_declared_key_name_matched`, and a hash binding the private manifest.
Neither keys, names, XML, offsets nor decoded content are exported. A cold final
validator verifies the closed source-bound finite report; it cannot recompute
private XML equality from exported counts/hash alone. That equality is the
pinned producer's validated observation, not independently replayable raw data.

The actual conservative serialized envelopes are1949/2048 projection bytes,
3092/12288 capture bytes with the full projection cap, and31832/32768 whole-report
bytes including all26 sources, full12288 capture cap, all lifecycle gates,
128-byte diagnostic majorants and final newline. Whole-report margin936 bytes.
Caps are unchanged. Tests must keep these bounds pinned and reject extra fields
or semantic promotions. All13 stages,11 snapshots,5 comparisons and4 cleanup
checks remain mandatory; later failures discard prior success.

Synthetic tests exercise cold flat staging, actual bounded reading of invented
file images, manifest lifecycle, independent mismatches, source changes,
cleanup failures and report validation without Docker, native execution or the
shared smoke fixture. A separately source-bound native run is still required
before reporting this binding as observed on the platform.
