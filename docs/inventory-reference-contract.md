# Inventory with typed catalog identities

Implementation checkpoint. Native reference semantics are **not yet measured**;
the scalar accumulation 16-observation baseline is not reference evidence.

The explicit `accumulation-reference-v1` grant is fresh-only format **15**. It
composes scalar, flat catalogs, posting documents (including typed header and
line CatalogRef fields), and Balance registers with typed CatalogRef dimensions
or attributes. Resources stay numeric. Catalog fields stay scalar. No forms,
CommonModules, independent managers, composite references, DocumentRef fields,
IR/accumulation combined configuration or migration is granted.

This is a distinct storage contract: catalog data/layout tables and numbering
sequences are populated; movement schemas have a new exact value-domain tag and
persist their target catalog UUIDs. Version 14 remains scalar-only, with its
original schema bytes and receipt hash domain. Changing only a version or marker
must never admit the other profile. Creation/open retain and reimport exact
source bytes, compare all projected schemas, and never execute source handlers.

A stored reference binds database, metadata target and record UUID, never Code
or Description. Nonempty targets must exist in the same borrowed transaction.
Empty references are typed, distinct from NULL/Undefined. This is a host integrity
rule; cross-database/family refusal and resource budgets are not native parity.
Movement JSON cannot rely on SQLite foreign keys for this check. Source guards,
coarse budgets, scalar validation and full reference validation are distinct.

One existing unit of work owns catalog/document writes, Posted, replacement
movements and durable receipts. A catalog created earlier in that transaction
can be referenced by its document. Savepoint cancellation rolls back all of the
posting operation; outer rollback also removes prior staged catalog creation.
Uncertain recovery resolves receipts and does not rerun document handlers.

Native gate: install the separately owned fixture, validate material redump,
then acquire 12 source-bound observation groups for typed defaults/assignments,
persistence, two-recorder receipts/issues, reference grouping/JOIN/equality,
identity despite equal or renamed descriptions, repost/ordinary write/unpost,
explicit movement write/query rollback and enclosing transaction rollback. The
old scalar observer remains unchanged. No semantic claim precedes that evidence.
