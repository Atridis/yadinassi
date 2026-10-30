# ValueTree Columns.Clear: bounded Linux lifetime model

`Columns.Clear()` / `Колонки.Очистить()` is a procedure with no arguments. The
Linux 8.3.27.1508 interpreter target now reproduces all original CC12 observations
and CL6 lifetime checkpoints exactly. The Python host OS is not the target:
Linux-target execution is supported on Windows Python too; Windows 1C target
lifetime behavior remains unmeasured and guarded.

## Observed model

Clear removes all active columns and rows. Held old row identities remain the
same objects, but Owner, Parent, Level, cell/named access and retrieving Rows fail.
Held old columns report empty Name/Title and Width zero. Other deleted-column
properties and setters remain guarded; no unmeasured ValueType or setter claim.

A row collection held **before Columns.Clear** retains its old Parent label but
routes the measured Count, Get, Add, Insert and Clear operations to the tree's
current root collection. Rows returned or created through those operations have
the normal active-root Owner, Parent and Level, independent of that saved label.
Multiple wrappers, deeper wrappers, root rebuilding and repeated Columns.Clear
were measured. The implementation uses an explicit per-wrapper marker and current
root routing, never case numbers, row names or particular fixture identities.

This marker is not set by ordinary Rows.Clear/Delete: their invalidated child
collections retain the prior guarded behavior. Old row access is not revived.
Other methods on Columns.Clear-detached wrappers (iteration, Sort, Move, Delete,
search, aggregation, load/unload) remain guarded; this is not universal forwarding.
The last-column Delete guard is unchanged.

## Safety policy, distinct from native observations

Columns.Clear performs an iterative, bounded structural preflight before mutation:
exact ownership/types, unique acyclic reachable rows, registry agreement, depth,
column/cell-key identity and existing row/column/cell/work limits. Cell values are
opaque and no equality, string, numeric or iteration hooks are invoked. Every measured forwarded operation prevalidates the active graph. Forwarded
Add/Insert additionally validate exact descriptor/qualifier types, finite numeric
metadata and cached-default budgets before invoking ordinary root insertion.
Root/owner and semantic-target guards apply to forwarding. These hostile-host-graph policies and
maximum-limit tests are local safety constraints, not claims of native parity at
all limits or a general transactional guarantee outside the observed cases.

## Evidence and ongoing tests

Fixtures in `tests/fixtures/value_tree_columns_clear/` preserve raw LF captures,
source/module hashes, original commits/runs and audit/provenance hashes:

- CC12: native run **41066943188**, 2252 bytes, SHA-256
  `4db4c7b231ca12b087ba6ff7e3a16069b0dffc27b5c35c12db7dc061d082460c`.
- CL6 (24 checkpoints): native run **41072087598**, 2820 bytes, SHA-256
  `ae2cba92a2129f9ba4695413aab6a739577bbef75b5283338d8552cd94ffddfb`.

Both acquisitions originally passed native evidence checks and failed runtime
parity before this implementation. Local exact server and generated-client replay
and strict production host comparisons now reproduce them; those local checks do
not relabel the original runs or claim fresh native execution. Fresh final CC12
native parity and platform CI remain required before merge.

The original required CC12 matrix row is restored. The exploratory CL6 matrix row
is retired, not its assertions: all six cases remain exact offline regressions,
and its immutable closed registry/source remain manually reproducible. No extra
permanent native job, full-suite change, permission change or cap increase.
