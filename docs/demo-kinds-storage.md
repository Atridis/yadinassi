# Partial exact-demo kinds storage (v6)

`SQLiteCatalogBackend.create_demo_kinds(path, files)` creates a **new** owned
SQLite v6 database from the complete original 19-file demo source mapping.
All original XML and BSL remain byte-for-byte in `configuration_file` and export.
Only `ВидыНоменклатуры` enters the active catalog schema and BSL manager inventory.
`Номенклатура`, `Склады`, their forms, and their modules remain archived and inert.
This is a deliberately partial application profile, not full demo activation,
general Designer import, or measured native parity. Ordinary create rejects its
partial-profile marker, including with activate=False. Existing v5 archives are
never upgraded or activated.

The `demo_kinds_v1` source profile pins every original path and SHA-256, including
otherwise inert files. Any addition, deletion, or byte change refuses admission.
The original kind catalog selects the local `decimal_v1` numbering contract:
code width 9 and description width 100. Existing v4 transactions, code counters,
write outcomes and receipts are reused without changing their formats. There are
no tabular-section capabilities in this profile and no new runtime module.

## Host/UI boundary

`active_form_catalogs()` returns the admitted catalog UUID tuple (empty on older
profiles). `read_form_source(catalog_id, expected=identity)` retrieves only the
admitted original default form; other source catalogs are refused. Opening the
backend pins the database/configuration identity, generation, source manifest,
active schema and layouts. Every ordinary read and write revalidates the exact
source. For writes this happens **inside BEGIN IMMEDIATE**, before any mutation;
the same lock covers source validation, numbering, data and receipt commit.

A UI retains the same backend instance and complete original form-source identity.
It must reject backend substitution, compare its original identity around form
preparation, and keep invalidated editors locked. This backend does not dispatch
form handlers by itself. The UI invokes the already bounded original form-event
consumer, then saves the resulting candidate through the ordinary object writer.
Programmatic BSL writes intentionally do not apply the form-only name rule.
No archived application or object module is registered or executed.

## Recovery

An uncertain write freezes its original request through the existing runtime
mechanism. On a retained, already-admitted backend, receipt-only reads can recover
the exact historical outcome even if source bytes were subsequently damaged.
They still validate the original database/configuration identity, generation,
name, partial-profile marker, schema and layouts, then match the retained intent
and outcome. This private read path rejects write transactions. No receipt means
only that the old operation is absent; a retry must pass full source validation.

Public reads, form preparation and new writes remain source-strict. Therefore an
already committed write can be confirmed while card refresh is blocked. The UI
must report that distinction, retain recovery state as needed, and never replay
BSL preparation or allocate another code. Normal reopening of a damaged archive
still fails: receipt-only recovery is not a recovery-only constructor and does
not authorize repairing source or silently changing a profile.

## Local evidence

Focused tests cover complete archive retention, one active catalog, original
form trim/refusal followed by real persistence/reopen, programmatic form-rule
bypass, source/generation drift, writer lock coverage, both uncertain-COMMIT
sides, read-only behavior and permanent v5 isolation. These are local SQLite/BSL
checks, not completion of all 12 native demo acceptance scenarios.
