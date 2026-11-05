# Inert configuration source storage

`import_inert_configuration(files)` and `SQLiteCatalogBackend.create_inert(path,
files)` preserve a bounded dictionary of original XML/BSL bytes without admitting
its executable semantics. The ordinary `import_configuration` admission rules
remain unchanged. Designer autonumbering, forms, object modules, subsystem and
language files can be archived, but no module is executed and no activation,
UI rendering, catalog record operation or native compatibility is granted.

## Durable boundary

Owned SQLite version 5 is reserved for inert source archives, separate from the
version 4 local-numbering profile. Reopen verifies version 5, inactive state,
exact inert marker, original source ownership and identity-only catalog stubs.
Stubs have zero code/description widths and no fields/sections; they are only
archive indexing, not an approximation of the source's executable schema.
Normal reads, writes, receipts, capabilities and migrations refuse this profile.
No conversion, migration or activation API is provided. The standard create API
also rejects active creation from an inert import result.

This reuses the owned-file creation transaction and uncertain-create cleanup
contract. Failed or uncertain creation never deletes a possibly committed file.
An incomplete retained file is not a successful archive and must pass reopen.

## Authenticated source retrieval within the owned-storage boundary

`backend.read_form_source(catalog_id, expected=None)` selects only the catalog's
explicit `DefaultObjectForm`. An empty default does not select the first form,
fall back to a list form or synthesize an automatic warehouse form. The catalog
must occur uniquely in Configuration.xml; its descriptor name/path/UUID, declared
form name, same-owner default reference, managed form descriptor and canonical
layout/module paths are checked. Unsupported layout internals remain opaque
bytes. A consumer must independently validate all semantics it executes,
including namespace-bound main-attribute catalog ownership and event handlers.

The frozen `CatalogFormSource` in `catalog_backend` contains an `identity`, names,
canonical paths, `default_object_form`, and exact `configuration_xml`,
`catalog_xml`, `form_xml`, `definition_xml`, `module_source` bytes. `module_present`
distinguishes an absent module from a present empty module. An absent optional
module is represented by empty bytes and false, never by invented source.

`ConfigurationSourceIdentity` fields are `database_id`, `configuration_id`,
`generation`, `manifest_sha256`, `catalog_id`, `form_id`. The manifest binds every
retained file's canonical path, kind, byte length and SHA-256 in a versioned,
deterministic encoding, including files unrelated to the selected form. Source
bytes, whole manifest and database identity are read and checked under one SQLite
snapshot. The connection is closed before returning; no lock spans UI/BSL work.

The open backend pins configuration identity/generation and manifest. Changes are rejected rather than silently rebinding. Stale identities or manifests
produce `schema_changed` and require reopening; malformed state produces
`integrity`.
Passing `expected=previous.identity` after reopening compares the complete source
identity again. `integrity`, `unsupported`, `closed` and `not_found` are refusals,
not permission to adopt partial state or bypass validation.

These hashes and bindings establish structural consistency and stale-snapshot
detection for owned storage. They do not authenticate against someone able to
rewrite the entire database and all hashes. A caller-provided DTO is not trusted
renderer input: the host must obtain it through this storage boundary.

## UI and future write integration

A UI consumer should retain dirty edits but stop new handler execution/state
adoption when source identity changes. It may recheck before and after a bounded
handler run without retaining a database transaction across the run. A prepared
candidate is not write authority. Any future database write must atomically
condition on the same database/configuration generation and required source
identity. An uncertain pending write remains locked until its original receipt
is resolved; source invalidation cannot convert uncertainty into safe discard.

This increment does not connect the renderer, run the actual demo end-to-end,
resolve its native numbering/section-query gates, or admit its modules for
activation. The archive itself is preserved byte-for-byte for that later work.
