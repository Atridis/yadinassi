# Additive configuration update: candidate design

Status: candidate host implementation. Canonical delta, explicit profile apply,
durable JSON plans and read-only status verification are implemented. No CLI or
implicit update is provided. No existing database changes on open. The initial physical transition is v11 to v12, retaining the base profile;
further configuration updates from v12 are explicitly refused in this increment.

## Closed input

An existing active v11 owned database retains its base profile. Both old and new
ConfigurationImport values must be exact reimports of their stored source bytes,
including the original numbering and executable-module opt-in. Authored logical
schemas with absent or divergent source packages are refused rather than having
XML synthesized for them. Catalog names/identities, existing field order/types,
qualifiers and identities cannot change. Existing sections, numbering, hierarchy,
documents, registers and executable modules remain identical. Only new scalar
catalogs with explicit numbering and append-only scalar attributes are admitted.
New attributes have closed qualified defaults: empty string, zero, false, or
DateTime's empty date. New reference fields are not part of the first profile.

## Implemented storage transition

The update uses an explicit successor physical profile, not extra tables silently
admitted in v11. Preserve the v11 retained base version and exact canonical
indexes; retain all existing UUID-to-physical-name mappings. Dry-run binds a
bounded complete source fingerprint, target canonical source package, deterministic
delta, physical mappings, defaults, migration identity and intended generation.
Apply requires maintenance, a verified backup and enough journal/rebuild space;
it recomputes the plan before opening an EXCLUSIVE transaction and rechecks the
source inside the transaction. Rebuild only changed scalar catalog tables using
canonical DDL, copy all old values unchanged, fill defaults and verify references,
counts, source/export parity and final admission before COMMIT. No writable_schema
or implicit schema repair. New catalogs use collision-safe allocations against the
complete preserved layout and reserved system namespace.

The new configuration generation invalidates previously opened managers/views.
Import profile conversion, feature-version promotion, removals, type conversion,
new non-scalar entities and activation of inert/demo profiles remain refused.

## Maintenance status

Physical v12 retains one configuration update marker recording the source
and target metadata needed to verify the additive transition. This marker
does not record business write operations. Current reads and writes use
only the latest canonical schema and generation.

Regression tests cover ordinary reads and writes across the update, interrupted
DDL/COMMIT, metadata and marker tampering, stale objects, unchanged non-catalog
rows and byte-for-byte source export. Target scalar and physical page limits
are checked before COMMIT; rejected updates leave the original database intact
when rollback succeeds.
