# UUID bounded alignment after the first authenticated native capture

Evidence: [PR112 native run40240060498](https://github.com/Atridis/yadinassi/actions/runs/40240060498),
head `f2c028681b191761e1f9cf3fc785960e7a58a534`, tree
`ce2f8ad3f3bc71b5bbff51fc1573dc1078d0fbdd`, native Linux8.3.27.1508.
The authenticated server and managed-client values outputs contain441 records.
All504 source files,24 staged input pins and62 runtime source files were audited.
The original run failed semantic comparison:21 UUID records agreed and18 differed.
That failed run is evidence of concrete observations, **not acceptance of this
updated implementation or a successful complete native gate**. Fresh CI/native
comparison is required after these corrections.

## Observed scalar contract

Russian and `UUID` names resolve; `UniqueIdentifier` is rejected. Type display is
`Уникальный идентификатор`; the display is not introduced as another lookup alias.
A fixed canonical lower/uppercase UUID string prints lowercase. Two separately
constructed identical values compare equal, a different UUID compares unequal,
and UUID is distinct from String. Map/FixedMap projections confirm value keys.
Zero UUID is not filled; the nonzero witness is filled. Empty, malformed, short,
braced and explicit Undefined constructor arguments fail.

Default construction produced canonical, nonzero, self-roundtrippable and distinct
values, and the observed version nibble was4. This supports the existing local
v4 generator on this measured platform; it does not establish entropy quality,
a collision guarantee, all generator versions or behavior on other platforms.
Random raw values are neither emitted nor golden expectations.

## Descriptor: singleton only

`New TypeDescription("УникальныйИдентификатор")` exposes one type and ContainsType.
AdjustValue with omitted input or Undefined yields zero UUID. UUID input retains
its value. The tested canonical String yields **zero**, not a parsed UUID.
The implementation extends these shape/type rules to canonical UUID values,
not a lookup of two captured constants. It accepts canonical string inputs only;
other conversion types/spellings remain unsupported. English singleton lookup is
consistent with the existing alias model, not a separately measured constructor.

Composite ordering, descriptor copy/qualifiers/array-construction, descriptor
codecs, type-value/descriptor ValueIsFilled and typed table/tree cells remain
unsupported. Shared typed-cell helpers explicitly reject UUID descriptors before
mutating columns, rather than accidentally enabling unmeasured cell defaults.
No UUID is inserted into the existing composite type order.

## Scalar codecs

Fixed and zero scalar writers and readback were independently observed:

- Internal UUID: `{"#",fc01b5df-97fe-449b-83d4-218a090e681e,<canonical UUID atom>}`.
- Internal Type writer: `{"T",fc01b5df-97fe-449b-83d4-218a090e681e}`.
- XML lexical value: lowercase canonical UUID text; inverse retains type/value.

The implementation uses bounded generic grammar and the observed type identifier,
not captured-string substitution. Only lowercase canonical UUID atoms are accepted
by these codec readers. Existing internal-stream separator whitespace remains
parser syntax; XML input is not trimmed. Quoted atoms, wrong arity, unknown type
IDs, malformed payloads and unsupported forms fail closed. Existing resource
budgets remain unchanged.

The Type-record inverse was not observed (only its writer was), so it remains
rejected. Nested UUID streams, UUID descriptor Pattern tags and cross-context
transport remain unsupported; no GUIDs, Pattern tags or conversion rules are
invented for them. UUID ordering and extended/versioned constructors are deferred.

## Verification boundaries

The unchanged441 source hash remains
`0030822843abe4e84d275fefcebc7a534d4e53fe43e671007a0848c7a28ee13c`.
Under the capture's explicit UTC timezone, complete updated host output replays
the authenticated native bytes SHA256
`2ffda9da54a4a598a011b738420c4de545670eddce14a2f59398f42fbfd2f23a`.
All39 UUID records agree; this is replay against existing evidence, not a new
native execution. The historical402 inverse, source admission, collections866,
Map exceptions, golden files, workflows and transport caps are unchanged.

Unit cases distinguish observed fixed/zero behavior from algorithmic canonical
model extensions and local unsupported-boundary tests. Packaged smoke includes
spaced display, scalar codec, zero descriptor default and XML roundtrip checks.
