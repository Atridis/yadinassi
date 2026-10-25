# Experimental bounded physical records

This independent standard-library slice is reconstructed from public source
`56e07ca0bb1862eed97efd5f1cede127e7f33965`, tree
`58d9cf8d7100688d0f05be34a91ade4c8330c119`. Earlier unpublished reader candidates
were lost in an environment rollback. Their historical files/tests are not
present evidence for this candidate. The restored source is left unchanged.
No third-party implementation code is copied, translated, or adapted.

## Explicit boundary

`read_records(read_at, file_size, *, profile, limits=None, catalog_limits=None)`
borrows a caller-owned consistent offline file. It never closes, writes, invokes
the native platform, traverses indexes, or guesses logical mappings. The caller
is responsible for consistency; read-only access does not establish it.

`RecordProfile(table_name, declarations, recordlock, format_item)` requires all
four inputs. Declarations are the complete exact ordered six-primitive physical
vector, including original names, case, nullability, declared length and scale.
The reader requires the exact selected table and exact vector before opening
its data object. Never construct a supposed expected profile by echoing an
unknown descriptor or by matching row values. Logical/native metadata mapping
is a separately reviewed integration responsibility.

Only lock token `"0"`, nonnullable B(16), RV(declared length 0), L(declared length
0), NVC(2/32), and N(9,2) are admitted. RV is 16 stored bytes and L is one stored
byte: those widths do **not** change measured declaration length 0 to 16/1.
Version fields precede other fields in declaration order; the leading status
byte and minimum five-byte stride are included. References and versions remain
opaque bytes. No hidden-version, nullable, other precision, fixed-string, BLOB,
or multi-type branch is implemented.

The seven-field fixture vector, if separately admitted, yields stride 127 and
original descriptor-order offsets `(17, 1, 33, 34, 50, 56, 122)`. This is a
predicted layout, not an independent offset measurement. The bounded accepted
fixture readback is described below; no names or suffixes are inferred from it.

The exact integer `0` is the sole predeclared experimental `format_item`
admission. Its semantics are unknown. String `"0"` is not equivalent. A mismatch
returns only a finite class: `format_integer_nonzero`, `format_string_zero`,
`format_string_other`, `format_list`, or `format_other`. The unknown AST/value
must never leave fixture isolation. Synthetic integer-zero inputs are not
native evidence.

## Header ownership and finite framing

Root page 2 remains the catalog internal file. After catalog parsing, only the
selected table's identity-bound, already range-checked `Files[0]` reservation
can be opened. It must have its own valid `1c fd` data header and supported FAT
level 0/1. All root/catalog/table reads and mappings share cumulative budgets
and disjoint page roles. No arbitrary page-number constructor is exposed.
Table BLOB/index headers remain reserved but unopened.

The following framing is fixed before native comparison, not selected after
looking for matching row values:

- `Files[0] == 0` is unsupported (`missing_table_data_header`), never root page 0
  and never an empty table inferred from failed opening.
- A fully validated existing data object with logical length zero is
  `empty_zero_length`. This is a documented source-justified revision from the
  lost earlier candidate's mandatory-reserved-slot assumption.
- Positive logical length must be an exact multiple of stride. Slot 0 must
  have marker 1. A single reserved slot is `empty_reserved`.
- Later slots must have status 0 (`reserved_and_active`). Any nonzero later
  status is unsupported. No freed-record payload is decoded. No deletion
  experiment or free-list traversal is implemented.

Physical free status is separate from logical DeletionMark. Boolean decoding
strictly admits bytes 0/1; native acceptance limited to false does not establish
coverage of logical deletion or physical frees.

## Independent format evidence versus experimental choices

All primary implementation references below are pinned to Tool1CD commit
`d5e31816f4c9b11a445f73fc92d08803840ce599`. They are externally informed format
facts, **not an official 1C specification or evidence that this Python reader
works on native files**. Only facts were used; upstream code was not retained
or incorporated. Exact bounded ranges were rechecked through the GitHub
connector during reconstruction.

- [FieldType.cpp 138–155](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L138-L155),
  blob `6137a2e3fe433c456a5370abac10c049872fe7fb`: fixed widths RV=16 and L=1,
  B=n, NVC=2+2n, N=(n+2)//2. Widths are independent of RV/L declared lengths.
- [Table.cpp 285–301](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L285-L301)
  maps lock `"0"`/`"1"` to false/true and conditionally adds a hidden version
  for true with no explicit version. This reader only admits false.
- [Table.cpp 418–448](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L418-L448)
  supports version-first ordering, then other fields in declaration order,
  leading status byte, minimum stride 5 and exact data-length divisibility.
- [Table.cpp 317–335](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L317-L335)
  identifies the first Files entry as the data object; zero means no object,
  not an address. Missing objects remain unsupported in this slice.
- [V8Object.cpp 163–218](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/V8Object.cpp#L163-L218),
  blob `824f10ad073ca84a19ccb6daffce4e0c595d77c3`: the addressed data header has
  its own `1c fd` signature, length/FAT information; length zero has no mapped
  data blocks. Header byte offsets/address units are inherited from the
  independently implemented catalog reader, not newly guessed row offsets.
- [TableRecord.cpp 96–99](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/TableRecord.cpp#L96-L99),
  blob `7ded7bf9508678f5b8fae622041b864bc3f1ec9e`: zero status means active.
  [Table.cpp 1802–1808](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L1802-L1808)
  initializes reserved marker 1 when writing into a previously zero-record
  object. It does not prove every newly created native table already has a
  reserved slot. Zero-length and reserved-only are separately pinned variants.
- [Table.cpp 188–190](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/Table.cpp#L188-L190)
  skips the format item with an unknown-meaning/always-zero comment, without
  checking its node type. Exact integer zero is therefore our independently
  predeclared restrictive hypothesis, not a proven semantic/version domain.
  All Table.cpp references share blob
  `3b5d0dfd2a5e19faac7fda6c12ade6d70472c5f7`.
- [BinaryDecimalNumber.cpp 47–77](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/BinaryDecimalNumber.cpp#L47-L77),
  blob `91ff9fe065fa8116b9318792a4678d95128eae56`: sign is the high nibble,
  zero selects negative, nonzero selects positive, and the first digit is the
  low nibble. Our narrower positive1/negative0, plain high-first BCD digits and
  declared scale2 are pinned experimental choices, not a claim about every
  writer/sign/complement variant. N9 consumes all ten nibbles, so no padding
  rule is needed. Exact Decimal tuple construction is independent of ambient
  decimal precision; no float conversion occurs.
- [FieldType.cpp 675–702](https://github.com/e8tools/tool1cd/blob/d5e31816f4c9b11a445f73fc92d08803840ce599/src/tool1cd/FieldType.cpp#L675-L702)
  supports a two-byte NVC length and Unicode conversion; it does not alone
  establish explicit byte order or code-unit definition. UTF-16LE and a
  little-endian UTF-16-code-unit count remain explicit hypotheses. Its signed
  prefix and our unsigned prefix coincide for admitted lengths 0..32. Strict
  decoding rejects invalid UTF-16; unused field slack is preserved, not decoded.
  The same source uses zero/nonzero Boolean interpretation; our 0/1 subset is
  deliberately narrower.

Native metadata capture can bind physical declarations and logical names, but
cannot by itself prove offsets or these binary codecs. Independently audited
native run 40184433888 at head `2973444c4234477429b05eb52831173a4745578a`
accepted six original/closed-observer baseline/created/updated fixture reads with
the same pinned mapping/profile and expected counts/four mapped values. Both
empty images had valid-header zero-length framing; reserved-only empty framing
remains synthetic-only. This is source-bound producer proof, not retained-DB
replay or general compatibility. See the exact source/profile/artifact hashes and
[acceptance limits](native-record-readback.md#accepted-source-bound-fixture-evidence).
No automatic alternative layout/encoding search follows a failed hypothesis.

## Outputs, budgets and standalone staging

`PhysicalRecords` contains an immutable physical table, validated data-file
metadata, stride, slot count, framing, ordered rows and cumulative catalog
usage. Each row retains slot, raw bytes and ordered `PhysicalValue` objects
with original declaration, offset, width, raw field bytes and decoded value.
These remain private caller-local results. Capability is always experimental
and native acceptance always pending; this module cannot certify itself.

Record limits default to 4096 slots, 4096 active rows, 4096 bytes/record and
16 fields. The fixture caller must explicitly set `max_active_records=1` and
require exact expected counts 0/1/1. Higher finite policy ceilings do not imply
native coverage. Catalog limits also bound reads, processing, output, and
cumulative mapping pages. Partial results are not returned on failure.

Do not import `yadinassi` for an isolated staged reader. Stage exactly the
verified `filedb_catalog.py` and `filedb_records.py` bytes under a private
synthetic package; install that package in `sys.modules`, load catalog first,
then records so its relative sibling import resolves there. A focused test
uses Python `-I -S -B`, hash-verifies both staged files, restricts imports to the
exact siblings and standard library, and rejects yadinassi/Interpreter/site
and third-party imports. This proves that loading contract on the test Python,
not a security sandbox, arbitrary deployment, or native environment result.

Synthetic tests use owned constructed bytes only. They do not establish native
compatibility, query support, v2 layout, deletion behavior or nullable encoding.
