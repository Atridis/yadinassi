# Owned inventory-reference acquisition

Owned source with native evidence from run43030189023 on 1C8.3.27.1508.
Immutable output/provenance: `tests/fixtures/native_inventory_reference/`.
Exactly **12 numbered observations** execute in one fresh isolated NativeSmoke
infobase only after official XML import, UpdateDBCfg and material redump.
No previous scalar-accumulation native16 fixture or golden is changed.

## Source and scope

Products and Warehouses catalogs, Receipt and Issue documents, one Balance Stock
register. Documents have Warehouse header and Lines(Product, Quantity, Amount).
The register has Product/Warehouse CatalogRef dimensions, numeric Quantity/Amount
resources and scalar Note attribute. UseInTotals=true; all posted movements active.
Catalog code length8, description64, no autonumbering/hierarchy. Explicit document
numbers, no real-time posting, selected movement writes and automatic unposting.

`native_source.py` preserves the checked-in native catalog and accumulation
wrappers, deterministic owned UUIDs, and complete candidate document section and
attribute wrappers from the repository demo. The Stock native2.4 derivative
retains MPL-2.0 attribution; its originals/license remain under
`../accumulation_register_behavior/public_source/vanessa_add/`. No third-party
module executes. The document section wrapper was accepted and materially verified by Designer
in that acquisition. Native source is still not accepted by the runtime.

`runtime_source/` is separately authored2.20 with the exact proposed
accumulation-reference-v1 grant; `runtime_source.py` reproduces it using only
explicitly selected properties. Metadata identities, fields, qualifiers,
recorder links and exact modules are shared; presentation/default wrappers are
not a runtime source-grant expansion. Storage format15 is a host contract.

## Twelve groups

1. Typed empty references on header, line and movement dimensions.
2. Wrong catalog assignment: rejection or transform, plus resulting old/empty
   identity, separately header, line and movement. No native outcome prescribed.
3. Ordinary write then fresh-object reference/value persistence.
4. Two products/two warehouses, independent receipts and Balance.
5. Receipt + Issue on one register, Balance and Turnovers receipt/expense/net.
6. Raw typed reference readback plus reference equality and catalog JOIN in both
   virtual tables.
7. Equal descriptions remain distinct; rename after posting preserves groups.
8. Fresh-object repost changes product and warehouse, replaces old group.
9. Ordinary Write on posted document preserves existing movements.
10. UndoPosting deletes only its recorder's rows, preserves a second recorder.
11. Explicit movement write is query-visible inside handler; Cancel and Raise
    each have independent raw/Balance rollback readback (two bounded subcases).
12. Outer transaction creates catalog item and posts document, queries inside,
    rolls back, then independently checks catalog absence and no movements.

Boolean facts and controlled numeric/code strings only, bounded ASCII results.
Unexpected setup/write/readback/query failure makes acquisition incomplete.
Wrong-type and intentional Cancel/Raise are measured catches, not expected-value
assertions. Nonce/order/entered/completed, source/host/configuration digests,
exact source admission and both process/container cleanup witnesses are mandatory.
No output becomes a golden automatically. No cross-database/stale-family/lifetime
host safety rule is claimed as native parity.

The new branch-gated workflow retains isolated pinned-image, non-root, no-network,
read-only-root and credential cleanup constraints from the existing route. No
workflow dispatch is enabled. The first native12 execution was announced by
the coordinator and source-bound to head4bef30e9 / admitted tree5dbb273f.
Future local/native execution still requires the coordinator's exact-count notice.

## Non-polymorphic observation selectors

Raw COUNT/SUM, fresh movement reference readback and inside-handler visibility
use the fixture-owned scalar Note tag `receipt:<Number>` / `issue:<Number>`.
Each document kind/number pair is unique in this source. No raw Recorder field
projection, predicate binding or union-reference runtime grant is required.
The tag is authored observation scaffolding, not a substitute storage identity;
repost/unpost/rollback still operate on the actual native recorder-owned rows.
