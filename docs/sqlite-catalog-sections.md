# Catalog tabular sections: SQLite storage contract

## Scope and evidence

This document describes the logical catalog backend and its owned SQLite adapter. A separate [bounded XML/BSL adapter](catalog-tabular-sections.md) now supports authored tabular-section metadata and detached runtime collections. Native row-number semantics, UI editing and configuration migration are not implemented. UI activation remains blocked for section-bearing databases; unsupported XML/module behavior still blocks activation. No native 1C section behavior has been measured for these increments; the semantics below are explicit yadinassi backend choices, not native-parity claims. No 1CD/CF/DT parsing or MongoDB physical schema is involved.

The internal format is not a public compatibility contract before a public yadinassi release. The v3 marker identifies this implementation; future development may change internal storage and project-owned fixtures. Native observation data is not rewritten to match the implementation.

`SQLiteCatalogBackend.create` creates v3 when the supplied `ConfigurationImport` (from the admitted XML subset or authored programmatically) contains a `CatalogSchema.tabular_sections` definition. Configurations without sections continue to create v2. Opening existing v1/v2 files does not change their format or data. Section metadata in legacy storage is rejected, not silently ignored. No v1/v2-to-v3 upgrade or metadata/schema-update API exists. The existing offline migration continues to handle v1-to-v2 only and refuses section-bearing source metadata.

## Logical types and write intent

- `TabularSectionSchema(identity, name, fields)` uses a metadata UUID. Each field uses `FieldSchema` and the existing exact string, Decimal, Boolean, whole-second naive datetime or fixed catalog-reference codec.
- `TabularRow(identity, values)` carries a nonzero row UUID, scoped to its catalog owner and section. UUID identity is independent of sequence position and all mutable names. Values are a tuple in the section schema's field order.
- `TabularSectionRows(section_id, rows)` identifies a section by UUID. Row tuple order is significant. A loaded `CatalogCard.tabular_sections` includes every declared section in metadata order, even when empty.
- `CatalogDraft.tabular_sections=None` means preserve all existing section contents. On create, there are initially no rows. This default preserves old client calls.
- An explicit tuple means replace all section contents. Sections omitted from that tuple are cleared; `()` clears all. Duplicate/unknown section IDs, duplicate row IDs within one section, invalid types and unrepresentable values refuse. String and Decimal values use the bounded [qualifier conversion](catalog-qualifier-assignment.md) before validation and SQL; storage decoding never truncates or rounds. No partial patch semantics are inferred.

`Capabilities.catalog_tabular_sections` is true only for an active v3 backend. A read-only v3 backend supports reading sections but no writes. Explicit nonempty section intents on v1/v2 refuse as unsupported. Owner and section fields use the same qualifier conversion; their exact supported types remain unchanged.

## Physical layout and names

There is one owner table per catalog, as in v2, and one additional table per `(catalog UUID, section UUID)`. For example, `catalog_section_Товары_Цены` contains:

- `owner_id`, a non-null deferred FK to that catalog's record UUID;
- `row_id`, a non-null row UUID;
- `row_number`, a positive integer representing current tuple order;
- one separately typed `attr_*` column for each section field.

The primary key is `(owner_id, row_id)` and `(owner_id, row_number)` is unique. Stored current row positions must be contiguous from one; this is an internal SQLite representation, not a claim about the platform's row numbering. Decimal/datetime fields use canonical exact text, Boolean uses a checked integer, and a typed empty reference uses SQL NULL. Nonempty references have deferred FKs to the metadata-declared catalog table.

Deferred FKs do not imply forward-reference support in the backend API. As with existing v1/v2 owner fields, nonempty section references are checked before inserting the owner. A section reference to its own new owner or to a target that has not yet been created is rejected. A target inserted earlier in the same transaction is visible to this check. Cycles can be formed by first creating the owners with empty references, then updating their references in the same transaction. These are current backend validation rules, not measured native 1C semantics.

`!todo`: define and test the intended create-time self-reference and forward-reference contract before changing this validation order; obtain separate behavioral evidence before claiming native parity.

The persistent `catalog_section_storage_map` and `catalog_section_field_storage_map` bind physical names to UUIDs. Allocation is readable, deterministic and collision-safe across owner/section/system tables, including Unicode-normalization and case collisions. All identifiers use the same quoted-identifier routine; all values use parameters. Physical names may retain a prior logical name. `inspect_section_storage_mapping()` returns catalog UUID/name, section UUID/name, table name and field UUID/name/column mappings without mutation. Legacy backends return an empty section mapping.

Renaming or reusing names does not rebind UUIDs. Reopening validates exact metadata identities, mappings and DDL, with no unexpected tables, views, triggers or explicit indexes. Tests that rename fixture metadata demonstrate identity isolation only; they are not an authorized schema-update workflow for real databases. Future configuration changes, new UUID allocation into existing databases and destructive migrations require a separate explicit planner.

## Atomicity, conflicts and recovery

Owner fields and explicit section replacements execute in the same write transaction under one optimistic owner revision. Every create/update also uses a savepoint covering SQL and its revision/receipt bookkeeping. A failure midway through row replacement or bookkeeping rolls back that entire owner write and restores the previous in-memory journal, so a caller may catch the failure and safely commit earlier successful writes after successful cleanup. Interrupted/failed cleanup poisons the transaction and prohibits commit. Stale revisions cannot alter either the owner or its rows.

Explicit replacement performs DELETE/INSERT of only that owner's section rows within the transaction. It never deletes the catalog owner. Setting `deletion_mark` alone preserves rows, references and the owner; physical catalog-object deletion is unsupported. No hidden tombstones are accumulated for section replacement.

Commit receipts include canonical section UUIDs, ordered row UUIDs and typed values only for explicit section intents. Section ordering is canonicalized by UUID, while row order stays significant. `None` retains exactly the previous seven-element owner request representation and its historical hash. Explicit empty replacement is distinct from omission. An uncertain COMMIT must be resolved from the persisted operation receipt after reopening; never blindly replay. A receipt is for the whole transaction, not separately for each section.

## Bounds

- At most 16 sections per catalog, 512 per database, and 64 fields per section. A serialized catalog schema remains bounded to 65,536 characters and all schema definitions to 16 MiB.
- At most 1,000 rows across all sections of one owner and 1 MiB of canonical encoded section payload per explicit owner intent.
- At most 10,000 supplied section rows and 16 MiB of section intents across one write transaction.
- Before materializing a card, SQL aggregates bound its persisted section rows to 1,000 and typed-column bytes plus fixed row overhead to 1 MiB. A full-card selection/scan additionally caps nested section rows at 10,000 and 16 MiB across its complete filtered result, not merely its current page. Unrelated owners do not consume that result budget. Full scans retain streamed integrity validation of unrelated section data without retaining its rows; scalar projections do not read sections. Overflow refuses; it never truncates rows or omits sections.
- Existing owner, metadata, file, SQLite schema and 256 MiB database limits still apply. Some limits overlap, so individual maxima are not guaranteed simultaneously.

All test data uses temporary owned SQLite fixtures. No real user database is modified by the test suite. Local fixture tests establish this implementation contract only; they do not replace future native behavior measurements.

## Read-only section scans

`CatalogReadView.scan_catalog_section(catalog_id, section_id, request)` reads one
declared section directly from its UUID-mapped table. It returns detached
`CatalogSectionRecord(owner, section_id, row)` values in `CatalogSectionPage`.
The existing typed `CatalogScanRequest` supplies predicates, ordering, page size,
continuation and string comparison policy. Its only standard field is `ref`,
meaning the owner `CatalogKey`; custom field UUIDs belong to the selected section.
No arbitrary SQL or physical table name crosses the logical backend boundary.

This is a v3 read-view operation, including read-only openings. Mutable write
views refuse it. The same pinned transaction and single-use continuation rules
apply as for catalog scans. Starting a new catalog or section traversal invalidates
the previous traversal on that view. Tokens bind the source kind, catalog and
section UUIDs, predicate, order, page size and string comparison policy. Equal
order keys use owner UUID followed by row UUID as an internal deterministic tie
breaker; neither native row order nor native line numbering is claimed.

Before payload fetch, the complete chosen section is checked for storage types,
encoded sizes, per-owner row positions, missing owners and dangling nonempty
reference fields. A missing owner is an error, not a row silently removed by an
inner join. Every row and every custom field is then decoded and validated before
predicates or pages are applied. A restrictive filter or TOP cannot hide a
malformed source row. The scanner does not load unrelated section payloads or
owner attributes, and is not implemented by flattening `scan_catalog` cards.

Source limits are 10,000 rows and 16 MiB of typed-column bytes plus fixed row
overhead, with at most 1,000 rows and 1 MiB per owner in the chosen section.
These are source-local read limits, not a whole-database audit or a relaxation
of the existing aggregate per-owner write limits. Pages contain at most 1,000
records. Canonical UUIDs, contiguous stored positions and scoped row identities
are checked even though row UUIDs and positions are not exposed to BSL.
Comparisons retain exact Decimal values and the existing typed reference scope;
string `casefold_v1` remains an explicit local comparison policy.

The [bounded BSL source](catalog-query-v1.md#read-only-tabular-section-source-local-contract)
adapts these rows to QueryResult. Native section-query behavior has not been
measured for this increment. It does not change XML activation, UI support,
configuration migration, or write/recovery semantics.
