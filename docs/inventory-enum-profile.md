# Explicit enum inventory storage

`inventory-enum-v1` is a fresh physical format 16. It is selected explicitly
with `--source-profile inventory-enum-v1` for `--check-xml` or `--create-db
--import-xml`. It does not migrate or widen formats 13, 14, 15 or their form
grants. Source bytes, catalog/document/register schemas and enum targets remain
part of admission on every snapshot. The private positive cache stores compiled
source only, never row-validation authority or a transaction lease.

## Useful supported slice

Catalog attributes, document headers and lines, accumulation dimensions and
attributes may name exactly one declared enum. Resources remain numeric.
Writes, typed-empty/member roundtrip, posting replacement/unposting/rollback and
fresh reopen use the existing unit of work. A value belongs to its root family,
context and generation: a matching UUID or equal fabricated object is not a
storage capability. Decoding returns the existing canonical manager reference.

The measured assignment adjustment accepts an owned reference from another enum,
ordinary bounded String, finite bounded Number or Undefined and returns the
canonical target empty. Boolean, Date and other unmeasured inputs remain refused.
Foreign, fabricated and stale enum objects are rejected before adjustment.
Storage codecs never coerce. Query parameters do not use assignment adjustment:
a canonical different-enum parameter is no match, not an empty-ref match.

Read queries support raw catalog/document/line/movement enum projections, exact
Eq/Ne, same-enum joins, NULL from unmatched outer joins, grouping, DISTINCT and
COUNT(DISTINCT), and enum-dimensional Balance/Turnovers/Day/Month statements.
Numeric resources retain the exact integer-coefficient reducer. Input validation,
row/cell budgets and current-owner snapshot checks precede filtering and TOP.

Enum ordering, MIN/MAX, mixed-enum field comparisons, enum conditional/membership
expressions, derived/external/temp/UNION/package paths and reference Unload remain
explicitly outside this initial slice. No enum UI/editor/transport grant, native
wire UUID codec, enum-valued numeric resource or arbitrary metadata XML is implied.

## Evidence and acceptance boundary

The immutable capture in `tests/fixtures/native_inventory_enum` comes from native
run 43086960484, source tree 859b834a0badea7abd2300e4a582282f3e3a1c2c.
Its twelve observations use two distinct Enterprise executions (11 then 1), each
with exit/quiet and module witnesses, plus owned container/private cleanup. The
original acquisition records `runtime_parity_accepted=false`; do not reinterpret
it as host parity. A separate unchanged-observer host replay and regression gate
must pass for the implemented runtime candidate. Earlier failed run 43083767249
had zero accepted measurements; typed-empty IndexOf serialization was corrected
without changing XML, handlers or acceptance gates.
