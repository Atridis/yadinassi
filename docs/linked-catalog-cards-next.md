# Linked catalog cards — local preparation, not new storage admission

Goal: a single read-only Products → Category business-card workflow with bounded
String/Number/Boolean/DateTime attributes and one fixed-target CatalogRef field.
Categories have zero custom attributes; products have mixed multiple attributes.
No writes, queries, hierarchy, composite types or tabular sections are exported.

## Implemented seam

`CatalogCardField` in `catalogs.py` is a private immutable **logical descriptor**,
not a CONFIG type token or a physical declaration. It projects already typed
values (str, Decimal, bool, BSLDate, UUID), preserving exact scalar types and
refusing implicit byte/string conversions. Reference targets are catalog metadata
UUIDs resolved through the same lazy Metadata snapshot as managers and types.
The target's generated native Ref TypeId is not accepted as a substitute.

Synthetic BSL tests cover selection → mixed values → linked Category.Description,
empty/absent targets, zero-attribute category, attribute permutation, typed
defaults, same record UUID in different catalogs, read-only behavior and invalid
logical-value refusal. They establish adapter behavior only, not native parity.

**The existing file reader remains unchanged:** CONFIG permits S/N only; its
binding/records compiler still admits the measured two-attribute shapes. It never
creates `CatalogCardField`. New field kinds or arbitrary attribute counts are not
advertised as readable from an actual `.1CD` yet. Existing slot, code ordering,
resource budget and exact declaration guards remain in force.

## One evidence batch, then finish the same block

The local packet `/workspace/shared/linked-catalog-cards-packet-v1` describes two
saved identity/order sets, category0attrs and product5attrs, empty/filled states,
Boolean defaults/values, DateTime defaults/values, and empty/present/absent typed
references. Existing host lifecycle/rights checks are to be reused, not replaced.

Official EDT 2026.2 platform 8.3.27 XDTO models now establish the generated
Designer input definitions: Attribute.Type is core TypeDescription, with direct
QName Type children; Boolean uses xs:boolean, DateTime uses xs:dateTime with
DateFractions=DateTime, and a single catalog reference uses the saved target name
in the current-config namespace. The pinned official CatalogRef API confirms the
reference namespace. Source hashes, model assertions and provenance are retained
in `/workspace/shared/linked-card-primary-research-v1/FINDINGS.md` and
`source-receipt.json`; this is schema-backed input, not observed platform output.

The packet keeps the existing native property shell and exact closed guards.
`!todo`: validate these generated inputs through native apply/CheckConfig/redump.
Capture the **applied redump**, actual generated
Ref TypeId and catalog metadata UUID separately. Independently retain CONFIG
attribute type descriptors, DBNames association, physical declarations/offsets,
raw slots and native scalar/type/lookup observations on the same frozen image.
Only then wire variable-attribute binding, Boolean/DateTime codecs and fixed-target
reference mapping into the public reader and replay the entire linked workflow.

`!todo`: composite references/types, hierarchy/owners, tabular sections, extra
date qualifiers and collation remain deferred. They must not be silently admitted
while generalizing the ordinary mixed-field path.

## Closed acquisition integration (local, unmeasured)

The source-owned `linked-catalog-cards-v1` selector reuses the existing reviewed
file-DB job, owner/exact-SHA gates, registry credentials and confined host lifecycle.
This dedicated feature source selects linked-catalog-cards-v1 for its reviewed
measurement; the original catalog-read selector remains available and unchanged
on main. No extra trigger,
credential boundary or caller database/source selector is introduced.

Two apply/redump installations and twelve bounded sessions cover the two saved
identity/order sets, empty/filled states and client/server contexts. Each context
runs four 24-row blocks in one session. Setup has 24 independent count/UUID/value
witnesses; its administrator audit remains separate from nonprivileged CRUD data
sessions. Native and offline readers use the same immutable postimage.

Reports bind the complete request and exact redump-generated type/metadata UUID
mapping, raw CONFIG descriptors, selected DBNames associations and physical table
bytes. This mapping is verified redump evidence, **not a decoded assertion that
an opaque CONFIG reference descriptor has that target**. DateTime/nullable/unknown
physical stride produces an explicit unresolved layout with no fabricated slot
counts or offsets. Bounded raw bytes survive for subsequent native-backed decoder
work. Matching unavailable observer errors cannot be reported as runtime parity.

Local tests use invented storage graphs and mocked lifecycle operations. They are
not native apply evidence. `!todo`: complete real apply/redump and linked-card
observations, then implement the measured physical types on this same feature.
