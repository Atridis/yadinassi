# Explicit source-profile import and preflight

This block exposes existing closed runtime profiles through one host import flow.
It does not accept arbitrary Designer exports or add XML schema semantics.

```console
python -m yadinassi --check-xml owned-source --source-profile accumulation-balance-scalar-v1 --report-json
python -m yadinassi --create-db application.sqlite --import-xml owned-source --source-profile accumulation-balance-scalar-v1
python -m yadinassi --f application.sqlite application.bsl
```

The five explicit choices are `legacy` (the unchanged default grant),
`document-recorder-scalar-v1`, `document-recorder-forms-v1`,
`accumulation-balance-scalar-v1`, and fresh-only format 15
`accumulation-reference-v1`. They are not fallback candidates. Selecting a
profile never strips unknown files or changes its original source digests,
canonical schema, transaction permissions or stored activation issues.

`--check-xml` reads and validates bounded source bytes, reports activation
blockers, checks deterministic creation budgets and compiles source-granted
handlers without executing them. It creates no database, connection, journal or
maintenance plan. A ready report is not a guarantee that the destination or
future filesystem operation will succeed, nor an authority token. Another CLI
invocation reads the source again. In-process creation reimports the exact
retained bytes rather than rereading a changed directory.

Creation remains exclusive and fresh-only. `--inactive`, numbering and common
module options retain their legacy scope; they cannot weaken the newer
grants. There is no migration, automatic index installation, application startup
or handler execution during import. Opening/ordinary script execution is a
separate action. Accumulation does not inherit the posting forms host grant.

Failures have a fixed code and stage and, where validation has established the
location, a source-relative filename, object, field and known property. Values,
source fragments, absolute paths, raw SQL and arbitrary exception messages are
not emitted. Unknown failures retain a generic refusal. Metadata locations and
the diagnostic list are bounded; unsafe locations are omitted, not cleaned into
a different plausible name. The stored `activation_issues` strings are unchanged;
only their host presentation is sanitized.

An unknown creation outcome still requires preserving the destination and
SQLite journal and inspecting them before any retry or deletion. A preflight
report cannot resolve that outcome or replay the write.

The low-level Python posting constructor keeps its existing admission timing.
The new explicit import workflow additionally compiles before allocating its
destination; it does not retroactively change historical constructor behavior.
Known parser error objects keep their original exception family and identity.
Their safe import location is ephemeral, not a stored schema or BSL error field.

See the exact [posting](document-posting-contract.md),
[posting/forms](configuration-posting-application.md) and
[accumulation](accumulation-register-plan.md) boundaries. In particular, measured
native acquisition XML is not automatically a supported runtime source package.

Local validation covers 266 focused tests and 1337 regressions both normally and
with Python optimization, including four real CLI create/reopen/byte-exact export
routes, lifecycle/query use, source refusal, and actual uncertain-create recovery.
This host workflow introduces no new native semantics or acquisition cases.

The separate [inventory-reference contract](inventory-reference-contract.md) adds
typed catalog identities without granting forms, enums or migrations. Its new
native reference observations are independent of the earlier scalar baseline.
