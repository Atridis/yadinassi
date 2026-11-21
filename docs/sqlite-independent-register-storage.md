# Native SQLite rows for independent information registers

A fresh SQLite database stores each independent register in its own
`ireg_<metadata UUID hex>` table. The revision and logical dimensions,
resources and attributes are separate columns. The schema-definition catalog
and sequence table retain their roles; no row/key JSON or shadow table is
written. Older physical layouts are not converted by this implementation.

Dimensions retain exact logical uniqueness. Strings compare case-sensitively
for key identity, and numeric signed zeros represent the same key. An empty
catalog reference remains SQL NULL; the unique index maps it to the zero UUID
only for key comparison. Nonempty references use the typed column's foreign
key. Decimal numbers use the shared scale-aware exact integer or sortable
16-byte binary representation, never floating point or TEXT.

Ordinary scans, selection and set membership use a deterministic native
dimension order. This order replaces serialization-dependent order of the
former JSON key. The record token remains a CAS revision; the key digest is
still computed from the canonical logical key in memory. The sequence and
logical write journal still make deletion/reinsert distinct and rollback atomic.

The native ordered TOP provider is limited to ordinary single flat independent
sources, without predicates, selecting/sorting bound fields. Explicit ORDER
uses the existing logical casefold and typed comparison semantics (with
dimension-key order for equal sort keys). The query provider validates each
selected full register row, like the other ordered TOP providers. Ordinary
scan/selection retain full-source validation and existing pagination/budgets.
Explicit transactions and virtual periodic slice requests use existing logical
paths over the same native table. No SQL expression or identifier comes from
caller text after binding.
