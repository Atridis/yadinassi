# Experimental partial Catalog identity projection

This opt-in private parser adds the embedded Catalog metadata UUID to the
existing Name and three standard-property prefix projection. Synthetic tests
alone do not establish native compatibility. No accepted native evidence for
this new identity contract is asserted here.

`yadinassi.storage.config_catalog_name.project_catalog_identity_prefix(data, *,
budget, limits=None)` returns a frozen private `CatalogIdentityPrefix`:

| Field | Zero-based path | Local admitted representation |
| --- | --- | --- |
| `metadata_uuid` | `[1][9][1][1][2]` | Nonzero bare ASCII UUID, normalized to lowercase |
| `name` | `[1][9][1][2]` | Existing nonempty Name scalar rules |
| `code_length` | `[1][17]` | Canonical bare nonnegative ASCII integer |
| `code_type` | `[1][18]` | Bare `0` (Number) or `1` (String) |
| `description_length` | `[1][19]` | Canonical bare nonnegative ASCII integer |

Only decoded immutable bytes and the caller's cumulative budget enter the
parser. Expected UUIDs, declaration keys, XML, filenames, readers and platform
APIs are not inputs. Parsing a UUID does not verify that it matches any external
declaration, nor does it establish the identity of an applied database object.

## Independently corroborated source-format facts

Pinned `saby-integration/v8unpack` revision
`deba8926fab78f67b8c362c010397a38967a2820` contains an executable read chain:

* [Catalog.py](https://github.com/saby-integration/v8unpack/blob/deba8926fab78f67b8c362c010397a38967a2820/src/v8unpack/MetaDataObject/Catalog.py),
  blob `d22a5bcdd8fdf50376baf5e9b95562ddf503f1d5`, selects the Catalog header at
  `[0][1][9][1]` in its decoded representation.
* [MetaObject/__init__.py](https://github.com/saby-integration/v8unpack/blob/deba8926fab78f67b8c362c010397a38967a2820/src/v8unpack/MetaObject/__init__.py),
  blob `00fc935bb0484e5f7033c02acd202572258644be`, passes that header to its
  header decoder.
* [helper.py](https://github.com/saby-integration/v8unpack/blob/deba8926fab78f67b8c362c010397a38967a2820/src/v8unpack/helper.py),
  blob `2fb94d176fe077ad879035544077f5fe1f12fa94`, reads the UUID at `[1][2]`
  relative to that header and validates it as a UUID.
* [json_container_decoder.py](https://github.com/saby-integration/v8unpack/blob/deba8926fab78f67b8c362c010397a38967a2820/src/v8unpack/json_container_decoder.py),
  blob `ee69f82809819079e43c2a502a97e81ffd8551a4`, appends the outer brace object
  to its returned list; the initial `[0]` is that list wrapper, not a child of
  the outer brace object.

Composing these observations yields the brace-object path `[1][9][1][1][2]`.
The same path is documented in a comment in the separately pinned
[DaJet CatalogParser.cs](https://github.com/zhichkin/dajet/blob/6af0c0baab11f9d281ad42a3eb2269d5b113cde5/src/dajet-metadata/parsers/CatalogParser.cs),
blob `67d3a6a23973301317c7d160e1adc35c41983e51`. The DaJet parser itself receives
this UUID externally; its comment alone is not executable identity evidence.
The standard-property paths retain their [previous source attribution](config-catalog-standard-prefix.md).

These are public implementation facts, not an official platform format
specification or native evidence for this parser. The implementation here was
independently written using the project's existing bounded cursor; no upstream
implementation was copied, translated, adapted, imported or executed.

## Deliberately narrow admission contract

The UUID consists of exactly 36 ASCII bytes: 32 hexadecimal digits and hyphens
at offsets 8, 13, 18 and 23. Uppercase hexadecimal digits are accepted and the
validated result is normalized to lowercase. A real comma or closing brace
must immediately follow it. Quoting, braces around the scalar, missing or extra
digits, other hyphens, non-ASCII text, URI prefixes and trailing whitespace are
rejected. Boundary SP/CR/LF before the token remain allowed. No UUID version or
variant restriction is inferred. Rejecting the all-zero UUID is a conservative
local identity-binding policy, not a universal statement about platform syntax.

The Name and integer grammar, numeric bounds and enum domain are unchanged from
the standard-property parser. A separate fixed-path iterative walk visits all
five fields once; it neither searches for UUID-shaped text nor builds a DOM.
Opaque branches do not retain scalar contents. Positional nulls are preserved.

The parser stops immediately after establishing DescriptionLength's comma or
close-brace boundary, without consuming it. Parent closes, remaining suffix and
EOF are unvalidated. This is not complete Catalog grammar, arbitrary metadata,
hierarchy, reference-type UUID parsing, applied CONFIG state or CRUD support.

The previous Name and standard entrypoints, their types, limits, error sets and
early stops remain unchanged, including their deliberate lack of UUID semantic
validation. New identity limits are not accepted as old limit types.

## Cumulative resources and privacy

`CatalogIdentityLimits` has the same lowerable ceilings as the standard parser:
4 MiB input, 131072 events, depth 64, 1024 UTF-8 bytes and 256 characters in Name,
and length values at most 2147483647. Effective depth intersects the existing
shared budget. Limits require exact integers, excluding bools.

Before cursor, stack, retained text or result allocation, the caller's existing
budget is charged `4 * len(data)` processing units and 131072 representation
bytes. Opening, closing, scalar and null events charge cumulative tokens before
growth. Failed attempts retain charges; there is no reset or refund. The fixed
reservation covers at most 64 frames, five fixed target paths of depth at most
5, bounded integer accumulators, 256 retained Name characters, the five result
fields and a 36-byte UUID slice plus bounded decoded/normalized copies. UUID
validation checks bytes before those copies are allocated. This reservation is
conservative admission accounting, not a Python heap measurement; no cap was
raised. The old Name reservation remains 65536.

`CatalogIdentityError` contains only closed finite codes (the standard parser's
set plus `uuid_syntax` and `uuid_zero`), never the raw UUID, Name or metadata.
The private result must not be included in public reports. A separate owned
native lane must compare the internal UUID with both the external declaration
and independently verified canonical XML, retaining only finite verdicts and
counts/hashes in its public evidence. Native acceptance must be bound to the
actual reviewed source, fixture and run, not inferred from older Name or
standard-property proofs.

## Separate owned native binding lane

The opt-in selector is `--config-catalog-identity-binding`, lane
`owned_config_catalog_identity_binding_v1`, invocation schema 20, report schema
31 and capture schema 32. It has a distinct policy and staged source inventory;
the old standard lane retains its existing schemas and proof scope. The
identity recipe is `config_catalog_identity_8380_8192_v1`, SHA-256
`815804b8bc0fa5f743554dc2250c3be6eda4027e7df8a2003f47c32a94c9662d`.

The shared private reader lifecycle resolves external Catalog declarations,
reads each selected entry's chain and decoded content once, and passes bytes
and its existing budget to the identity parser. It reserves 262144 bytes for
at most 256 private key/result associations before allocation. Every selected
entry must complete successfully, including later entries, before a private
result is returned; failure poisons the chain/decoder and returns no partial
evidence. Previous Name and standard observers use their unchanged contracts.

The separate comparator requires exactly one Catalog in this owned fixture.
It checks the parsed internal UUID against the external declaration key, then
that key against the independently verified canonical XML Catalog UUID. Name
and the three standard fields must match as well. Expected XML values never
enter the byte parser. XML identity validation retains its exact shape,
namespace, source hash, nonce and canonical-document checks. Equality failures
are finite diagnostics, not UUID-bearing messages.

The public result retains the existing external-key/Name verdict and adds the
lane-specific finite `catalog_identity_validation` value
`owned_uuid_code_description_matched` instead of the standard lane's field.
No raw UUID, Name, numeric property value, XML or decoded CONFIG is exported.
All 13 stages, 11 snapshots, 5 comparisons and 4 cleanup steps remain mandatory.
Synthetic envelope tests measure projection 2020/2048 bytes, capture
3096/12288 bytes, complete report 31852/32768 bytes and failure capture 118
bytes. These are protocol admission checks, not native semantic proof.

Before claiming native acceptance, use a separately reviewed source-bound
dedicated run, validate its production report first, and independently check
its source/staged inventory, finite verdicts, lifecycle and cleanup evidence.
The ordinary runtime lane and older standard-binding run cannot substitute
for this run. Activation changes only the dedicated workflow's selector from
`--config-catalog-standard-binding` to `--config-catalog-identity-binding`, with
an exact-delta assertion. The image, permissions, admission checks and cleanup
remain unchanged. This does not itself advance the reviewed runner branch or
establish native readiness: final source binding, independent frozen readiness
checks, local full gates and a dedicated native run remain required. Credentials
and access are unchanged.
