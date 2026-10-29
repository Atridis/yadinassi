# Catalog row-reference UUID codec (local implementation boundary)

`yadinassi/storage/catalog_reference_uuid.py` provides two pure operations:

- `decode_catalog_reference_uuid(physical: bytes) -> uuid.UUID`
- `encode_catalog_reference_uuid(value: uuid.UUID) -> bytes`

The decoder requires exact immutable `bytes` of length 16; the encoder requires
an exact standard-library `UUID` with a valid 128-bit integer. Neither accepts
subclasses, strings, mutable buffers, implicit coercion or user conversion hooks.
`CatalogUUIDError.code` is one of `bytes_type`, `bytes_length`, `uuid_type`,
`uuid_value`; diagnostics never include input values. No I/O is performed.
Every bit is preserved, including UUID variant/version bits; neither operation
supplies a version argument to the UUID constructor.

## Direction and evidence

For canonical UUID bytes `c` and physical reference bytes `p`:

```
c[i] = p[(12,13,14,15,10,11,8,9,0,1,2,3,4,5,6,7)[i]]
p[i] = c[(8,9,10,11,12,13,14,15,6,7,4,5,0,1,2,3)[i]]
```

The mapping is not Python `UUID.bytes_le`. It matches the two independently
created distinct-byte Catalog observations in PR146's paired native run
40898415637, attempt 1, source `ceebcc8b06601ab8a59b2dd2fdcba26e3f7d22a3`,
tree `5c1cdca58aade8e8ded2312f77e5bb82c60da9ae`.
This supports a narrowly measured row-reference byte order, not arbitrary
`.1CD` files, all object types or all field layouts. The byte reader must still
admit a concrete layout independently. The codec is not connected to the
Catalog reader, interpreter UUID value, or a BSL Catalog manager in this change.

The measurement remains measurement-only (`codec_approved=false`). Its reports
publish observed permutations and finite predicates, not raw private native
UUID/physical-byte witnesses. Unit vector constants derived from the observed
mapping are algebraic regression tests, **not replay of private native bytes**.
Zero and all-ones unit cases likewise prove conversion algebra only. Native
logical zero-UUID/empty-reference observations do not prove the representation
of a persisted empty-reference-valued field: the baseline had no active row.

## Separate native verification route (implemented locally, native run pending)

Do not alter schemas 39/40/41, their acceptance rules, existing measurement
entry points, or their ability to retain unexpected valid permutations. The explicit codec-verification profile uses invocation schema 25, report 42,
capture 43 and aggregate 44, with a fixed 42-source inventory including this
codec. Review its implementation and freeze the checker before native use.

1. Retain the measured profile's two fresh independent cases, owned databases,
   lifecycle, immutable-image hash joins, actual committed UUID sidecars,
   origin/observer reads and strict cleanup. Admit and finish the byte reader
   before importing or calling the codec. Never pass an expected UUID to the
   reader, replace the native witness with the requested UUID, or manufacture
   physical bytes from the reported permutation.
2. Inside the private run, for each independently admitted physical reference
   `p` and the matching actual committed native UUID `u`, check **both**
   `decode(p) == u` and `encode(u) == p`. A round trip alone is insufficient:
   mutually inverse but wrong codecs can pass it. Evaluate create and update,
   origin and observer, in both cases; a missing witness is failure, not skip.
3. Export only bounded booleans/counts plus authenticated source/run/image and
   case joins, with explicit success requiring every comparison. Never export
   raw UUIDs, physical fields, native logs or database images. The new checker
   must reject a missing case, codec source mismatch, partial stage coverage,
   wrong direction, encoder-only/decoder-only failure, malformed lengths/types,
   and all-success booleans disconnected from the required evidence chain.
4. Authenticate external commit/run/artifact identity, run the exact-source
   production finalizer cold, then the frozen independent checker. Pin and
   verify codec source alongside measurement sources; no acceptance inherited
   merely because the old measurement or an unrelated CI job was green.

The existing public reports no longer contain the raw witnesses required by
step 2. They support the mapping hypothesis and provenance but cannot prove
execution of this new encoder/decoder against those private bytes. If original
private inputs are not retained under the same authenticated source/image
joins, obtain **new** paired native witnesses through the reviewed new route;
do not claim a retrospective native codec pass from permutation-only reports.
The old measurement route remains separate. The new CLI is
`--catalog-reference-codec distinct_a` (or `distinct_b`), with fixed codec-prefixed
outputs. Before case B credentials, `--validate-codec-a` authenticates the
artifact handoff. Per-state `codec` is four positional finite symbols: origin
decode/encode, observer decode/encode. Baseline requires `NNNN`; created and
updated require `TTTT`. The aggregate requires both distinct cases and nonces.

Only the new capture schema has the stricter 8192-byte cap. The complete
42-source/lifecycle envelope with the entire capture cap and trailing newline
is bounded by 28667 bytes, below the unchanged 32768-byte report cap. Old
capture schema 40 retains its 12288-byte cap. All witness, token, image and
source joins remain; no raw UUID or image data is exported.

## Local checks

`python -m unittest discover -s tests -p test_catalog_reference_uuid.py -v`
(and the same under `python -O`) covers two explicit non-symmetric vectors,
all 128 one-bit basis vectors in both directions, 1,024 deterministically
seeded two-sided round trips, zero/all-ones algebra, strict type and length
admission, malformed UUID objects, finite diagnostics and stdlib-only imports.
Full project gates and the native route remain separate acceptance
requirements; a local unit pass alone is not native codec acceptance.

## Dedicated workflow selection

The reviewed-push file-DB workflow now selects the codec lane explicitly in
source (`catalog-reference-codec-v1`). This is an intentional workflow default
change, not a claim that its previous scheduling is unchanged. The identity
measurement jobs and their commands remain available under the other fixed
selector, with their permissive measurement semantics intact. Only one pair
runs per reviewed push. Unknown or missing selectors fail admission; the final
verdict requires both selected jobs successful and both unselected jobs skipped.
The new B job authenticates the exact A artifact/current run/attempt/digest and
source before credentials. Trigger, owner/ref/SHA admission and isolation
permissions remain unchanged. No native codec run has yet been accepted.
