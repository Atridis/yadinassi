# Explicit source-profile import and preflight

This block exposes existing closed runtime profiles through one host import flow.
It does not accept arbitrary Designer exports or add XML schema semantics.

```console
python -m yadinassi --check-xml owned-source --source-profile accumulation-balance-scalar-v1 --report-json
python -m yadinassi --create-db application.sqlite --import-xml owned-source --source-profile accumulation-balance-scalar-v1
python -m yadinassi --f application.sqlite application.bsl
```

The four explicit choices are `legacy` (the unchanged default grant),
`document-recorder-scalar-v1`, `document-recorder-forms-v1`, and
`accumulation-balance-scalar-v1`. They are not fallback candidates. Selecting a
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
module options retain their legacy scope; they cannot weaken the three newer
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

Implementation checkpoint: validation is pending; no new native parity claim.
