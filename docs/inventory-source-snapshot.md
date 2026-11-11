# Current-view inventory source data

The exact full-source physical15 forms grant now exposes `inventory_source`
on its owned SQLite read view (and its exact document wrapper). This port
returns the immutable configuration proved by **that view's successful current
admission**, not a later backend attribute or a prepared importer cache entry.
An optional `expected` value is compared using a closed exact-type immutable
walk; arbitrary equality, coercion and presentation hooks are never invoked.
Explicit `None` is not an omitted expected value.

Each actual begin still reads/hashes all current source bytes and checks the
profile, database identity/generation, schema/DDL and existing movement/storage
requirements. The positive importer cache avoids recompilation only after this
current proof. It is not a row integrity certificate. Existing row validation,
budgets, raw-edit detection, write receipts and uncertainty remain unchanged.

The proof belongs to one exact live read owner and connection. Close, poison,
rollback and failed cleanup revoke it. Failed physical close retains the
existing busy owner until cleanup succeeds. Writers, transaction-borrowed
read subclasses, foreign/copied owners, old scalar profiles and core15 do not
receive this port. Immutable returned data may outlive the view but is merely
expected data for the next actual admission, never root/write authority.

Inventory root verification combines its existing source and schema checks in
one read phase. Root-context checks, journal preparation and final root-entry
checks stay separate. Reports/choices reuse their existing current read owner
instead of importing the same full configuration a second time. Catalog editor
checks keep stale/schema/identity fences in one read view. Document/catalog
construction adopts admitted source data without caller-side reimport. No
whole-RPC memoization, implicit transaction, global cache, migration or new
format is introduced.

## Measurement protocol (pending execution)

Compare identical frozen source grants on the whole statement/UI union plus
prepared forms cache, versus the same input with this port and caller adapters.
A new actual Controller -> encoded Broker driver has two independent scenarios:
23 business RPCs creating catalog items and a one-line Receipt (26 with hello
and cleanup), and a public-BSL seeded 32-line Receipt exercised through real
open/edit/post/report/choice/statement/close requests (15 RPCs). Setup is outside
measured phases. The historical 23-RPC diagnostic was one line, not 32 lines,
and had no compilation counters or elapsed time.

Count canonical/full imports, form compilation, export, begin and admission
using observation only. Preserve semantic audits and exact head/tree/driver/
source bindings. Startup and warm phases remain separate. Instrumented phase
walltime is not a production benchmark or exclusive compiler attribution.
No measured speedup is claimed until the frozen A/B execution succeeds.
