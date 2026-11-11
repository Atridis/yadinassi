# Optional exact-read indexes

The read bundle is an optional, closed set of nonunique indexes. Existing files
without it remain readable. Admission accepts precisely the baseline or baseline
plus the entire known bundle, including exact names and SQL. Partial, altered,
or unknown indexes are refused, never repaired while reading.

The bundle indexes catalog code and description with `yadinassi_casefold_v1` for
Query and adds BINARY description equality for public exact lookup, then logical
UUID order. Public FindByCode keeps the existing UNIQUE BINARY code autoindex (SQLite supplies the final rowid tie-break). Bare layouts
also receive the existing catalog UUID-order indexes. Document layouts receive
a casefold-number query index and, when not mandatory already, the date-order
index. This does not change BINARY FindByNumber semantics or ambiguity refusal.
No format/user_version or configuration-generation increment is introduced.
Index availability does not eliminate cold integrity validation. For public
FindByCode, the new saving is connection-local validation reuse: the first
1000-row lookup still validates 1000 scalars, while ten unchanged warm lookups
perform zero scalar-source decodes and use the existing UNIQUE code index. New
indexes serve casefold Query predicates and exact Description lookup instead.

## Explicit maintenance

Stop application owners and retain a verified backup. SQLite locks protect active
transactions, not idle owners. Keep maintenance exclusion through resolution.

```python
from yadinassi.sqlite_query_index_maintenance import prepare, apply, resolve
plan = prepare(path, maintenance=True)
apply(path, plan, maintenance=True)
# Only if the apply outcome is unknown:
state = resolve(path, plan, maintenance=True)
```

Preparation is read-only and deterministic. Its plan binds database identity,
configuration generation, format, schema cookie, file device/inode, complete
schema/data/rowid fingerprint, and the exact closed index declarations. Apply
regenerates the plan, then checks again under an exclusive transaction. The
bundle is installed atomically. Plans containing arbitrary SQL cannot authorize
execution. Existing owners detect the changed schema; reopen them after apply.

A failed commit acknowledgement is `uncertain_commit`. Resolution never replays
DDL: it classifies the exact unchanged source as `not_committed`, the exact target
as `committed`, and other states as `uncertain`. This proves achieved state, not
which process installed it. Later data changes intentionally prevent resolution.
An already installed bundle is not a new installation request. File identity
checks are fail-closed guards, not protection against a malicious same-user
filesystem race. Configuration table rebuilds preserve an installed full bundle.

For an explicitly requested new base-layout database, use
`SQLiteCatalogBackend.create(path, configuration, query_indexes=True)`. The
ordinary default is unchanged and creates no optional indexes. Source-profile
convenience constructors and profiled posting/accumulation creation retain their
existing behavior; install the bundle afterward through maintenance.

The older base-to-v11 format plan is deliberately refused when this optional
bundle is already installed, because its mandatory UUID/order additions overlap.
Choose the format migration first, then install this bundle. This is an explicit
supported-order boundary, never an implicit drop/rebuild during open.

External SQLite writers must register the versioned collations before modifying
indexed values. The owned writer does so already; optional indexes do not grant
generic tools permission to substitute a different comparison implementation.
