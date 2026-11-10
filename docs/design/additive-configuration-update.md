# Additive configuration update: candidate design

Status: canonical delta implementation only. Storage apply, recovery and CLI are
not implemented by this checkpoint. No existing database is changed on open.

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

## Planned storage transition

The update needs an explicit successor physical profile, not extra tables silently
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

## Historical receipt invariant

A metadata update must not make a previously committed but unacknowledged write
unresolvable. Catalog request hashes were calculated with the old ordered field
schema; revisions and mixed-unit hashes also bind the old generation. Merely
keeping receipt SQL rows or accepting the current schema is insufficient.

The successor profile therefore needs bounded immutable generation metadata and
receipt-to-generation bindings for existing catalog/document/register/unit receipts.
Resolution must select one retained generation using the exact operation identity,
validate its source/schema, and compare the original request and child outcomes
with the original schema/generation. Historical readers are receipt-only: they may
not authorize writes, source execution or current data projections. Current reads
and writes use only the latest canonical schema and generation. Altering a retained
request must remain a conflict. Historical schema selection must never be guessed
from tuple length, revision token, catalog name or a successful hash collision.

The exact storage API and admission table schema are still under review. Tests
must cover committed/uncertain old writes and mixed units across an update, changed
requests, interrupted DDL/COMMIT, metadata/marker tampering, stale objects, unchanged
non-catalog rows and byte-for-byte source export. No recovery support is claimed
until those paths are implemented and verified.
