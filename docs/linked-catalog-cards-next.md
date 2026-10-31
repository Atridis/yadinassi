# Linked catalog cards: bounded read-only workflow

The reader now supports selection and exact lookup of product cards with mixed
String/Number/Boolean/DateTime attributes and fixed-target catalog references,
including traversal to a zero-attribute category. No database mutation, query
runtime, transaction or authentication capability is added.

## Native evidence and implementation

Native measurement run **41227322065**, source
`4e5ddc7d2eacfc59bec28931c97cad23a4274543`, report SHA256
`6940e058ec877f0a32946ee50f6d5fa161dd6b716553ea2e23db0c26b86d4499`
contains two randomized identities and reversed attribute orders, empty/filled
states in client/server contexts, actual apply/redump and same-postimage CONFIG,
DBNames, declarations, raw table bytes and 32 available BSL observation blocks.

The historical S/N projector remains unchanged in admission. A separate linked
CONFIG entry point admits B(), D(), and #(nonzero bare RefTypeUUID). The owning
catalog generated reference type is read at header route (1,3). The complete
same-source CONFIG snapshot resolves target RefTypeUUID to catalog metadata UUID;
unknown, duplicate or metadata-UUID substitutions fail before table payload reads.
Catalog UUID, type UUID and record UUID are never interchangeable.

The linked physical profile has String CodeLength2, DescriptionLength8 and at
most ten custom attributes (the existing 16-field ceiling). Zero and five mixed
attributes are natively measured; other counts within the ceiling are structural
compositions of the admitted fields. Existing bounded S/N qualifier ranges remain
structural generalizations. B uses strict L0/1; DT uses seven packed decimal bytes
YYYYMMDDhhmmss with the measured all-zero empty-date encoding, rejecting invalid
BCD/calendar values. Fixed references require the exact B16 `_FLD<id>RREF`
declaration. UUID conversion is invoked only for that bound reference role.

Runtime maps physical datetime to BSLDate and reference bytes to a catalog-bound
BSL reference using the same lazy metadata snapshot. Selection, reference fields,
TypeOf/equality/ValueIsFilled, typed defaults and absent target references reuse
the existing immutable manager/reference/cursor behavior. Existing code ordering,
0/1 free-slot liveness, declaration matching and resource bounds are preserved.

## Regression evidence boundary

`tests/fixtures/linked_catalog_native.json` retains source-bound raw CONFIG and
physical/native observations. `test_linked_catalog_native_replay.py` reconstructs
**synthetic transport** around exact captured CONFIG/declarations/slots and runs
all 32 native BSL blocks through FileDBContext; this is not a saved native .1CD.
`linked_catalog_records.json` separately replays both physical orders and checks
strict date decoding, nullable rejection, forged bindings and unchanged free
chain guards. The final composed source still requires coordinated actual
frozen-.1CD parity and aggregate gates before publication/merge acceptance.

# !todo Composite/nullable references, hierarchy/owners, tabular sections,
additional date qualifiers, other linked standard-field shapes, arbitrary
collation and multi-node free lists remain unsupported; no silent fallback.

## Actual frozen-image parity checkpoint

The completed linked runtime on `b7427c58c9315fe2a681fe83083edd842a227ea7`
passed [native run 41241917118](https://github.com/Atridis/yadinassi/actions/runs/41241917118):
32/32 observer blocks and 768 deterministic observations matched the real
`FileDBContext` reader on the same immutable native `.1CD` postimages. Both schema
identities, empty/filled states and client/server contexts were covered; all 129
source identities and cleanup were independently verified. This is distinct from
the earlier synthetic-transport replay. The subsequent XML/main source union must
obtain fresh source-bound parity before its merge; this checkpoint is not relabeled
as evidence for another runtime bundle.
