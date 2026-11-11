# Explicit additive configuration update

This host-only maintenance API updates an active owned SQLite **v11** database to
physical **v12**, retaining its original feature profile (2, 3, 4, 7, 8, 9 or 10).
Opening a database never applies an update. This increment permits one update from
v11; further updates from v12, feature conversion, and inert/demo activation are
refused. It is not a generic configuration migration engine or native parity claim.

## Supported change

Provide a complete canonical XML/BSL package for the same configuration UUID and
name. The permitted delta is a new scalar catalog with explicit numbering, or
appended scalar attributes on an existing catalog. Existing UUIDs, field order,
qualifiers, names, physical mappings, sections, numbering, hierarchy, documents,
registers and executable module bytes must stay unchanged. Reference attributes,
removal, renaming, type changes and arbitrary DDL are unsupported. Authored schemas
without corresponding canonical source packages cannot be used as an update source.

New attributes use qualified empty string, zero, false or empty DateTime defaults.
Old record identifiers, revisions, values and receipts are preserved. The target
must satisfy the same data and file budgets as ordinary readers **before COMMIT**;
backfill that would make a catalog unreadable is rolled back, not accepted as an
uncertain successful migration.

## Maintenance workflow

Stop every process using the database, retain a verified independent backup, and
allow disk space for table rebuilds and the rollback journal. SQLite's exclusive
writer lock does not exclude a dormant application holding stale objects. Keep
maintenance in effect until apply or recovery has been resolved.

```python
from pathlib import Path
from yadinassi.configuration_import import load_configuration_directory
from yadinassi.sqlite_configuration_update import (
    prepare, dump_plan, load_plan, apply, resolve,
)

# Preserve the source's existing explicit import/numbering/module policy.
target = load_configuration_directory("updated-source", numbering_policy="decimal_v1")
plan = prepare("owned.sqlite", target, maintenance=True)
print(plan.added_catalogs, plan.appended_fields, plan.source_generation)

# Retain exact bytes durably before apply. Never overwrite another recovery plan.
with Path("update-plan.json").open("x", encoding="utf-8") as stream:
    stream.write(dump_plan(plan))
    stream.flush()
    import os
    os.fsync(stream.fileno())

apply("owned.sqlite", plan, maintenance=True)
```

For an existing CommonModules runtime profile, supply its existing `module_runtime`
argument when loading the target; this update does not grant a new execution profile.
The JSON plan contains complete source code and metadata. Keep it private when the
configuration is private; this API does not upload it or create a backup.

`prepare` is read-only and binds the full source fingerprint, canonical target,
operation identity, exact delta and preserved physical mappings. `apply` recomputes
that plan, then rechecks inside the exclusive transaction. Changed source means a
conflict, not a best-effort update. Do not retry an `uncertain_commit` blindly:

```python
retained = load_plan(Path("update-plan.json").read_text(encoding="utf-8"))
state = resolve("owned.sqlite", retained, maintenance=True)
# committed / not_committed / uncertain
```

`committed` requires admitted current storage and the matching durable update
marker. `not_committed` requires the unchanged original v11 fingerprint. Missing,
changed or inaccessible evidence means `uncertain`; investigate while maintenance
remains in effect. Repeated resolve performs no writes.

## Generations and historical receipts

The update increments configuration generation, invalidating old managers and
write revisions. Reopen current application contexts after maintenance. Old
unacknowledged catalog/document/register and mixed-unit operations remain resolvable
with their **original** operation IDs, drafts and revisions. A bounded immutable
receipt epoch map selects the old canonical schema/generation only on internal
receipt-resolution paths. Historical schemas cannot authorize current writes,
Query execution or source activation. Changed requests still fail. New operations
use the new generation and expanded schemas.

The initial read integrity pass remains mandatory. The update does not bypass
query limits, cache validation across writes, repair corrupt source data, or promise
indexes for arbitrary predicates and sorts.
