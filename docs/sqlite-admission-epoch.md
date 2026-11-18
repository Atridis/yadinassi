# Format16 read-admission contract

Format16 retained readonly handles reuse a successful source/schema admission
within one **actual connection-local SQLite data epoch**. This intentionally
changes the previous requirement to re-read/hash all source bytes and physical
metadata on every read lease. PreparedSource itself is still only an importer
cache; it does not attest to live SQLite state.

The admitted descriptor contains detached source, schema, enum-domain and layout
values. Before reuse the backend's values must still match it. A descriptor does
not admit a different configuration, execute stored code, grant a transaction or
prove the validity of catalog/document rows. Row integrity proofs remain in the
separate bounded read-handle proof dictionary. Full source admission still checks
against the backend's original configuration, not whatever new source a foreign
writer stores.

## Snapshot and invalidation

1. Check file identity and owner; BEGIN on the retained readonly connection.
2. Read sqlite_schema to acquire a real read snapshot (BEGIN alone is deferred).
3. Require DELETE journal mode and query_only, then sample main.data_version.
4. On a cold/changed epoch perform the complete existing admission. On a matching
   epoch compare the detached in-memory descriptor instead of rereading source.
5. Publish only after confirmed ROLLBACK, under the **old pinned epoch**. Never
   relabel a proof with a data_version read after the rollback.

External SQLite commits which change database pages invalidate the connection's
data_version and force complete admission on the next read. A no-op SQL UPDATE
may leave the epoch unchanged because there are no changed pages. Own writes
invalidate even if subsequently rolled back. New connections/backends start
cold; failures/interruption retire or invalidate their proofs. File replacement
is rejected. WAL is not supported by this contract.

This relies on normal SQLite coordinated writes, SQLite locking and the existing
private-file boundary. Arbitrary raw writes bypassing SQLite locks, hostile
filesystem rollback, or in-process mutation of private proof objects are not a
supported cooperative-write protocol. A stored generation/digest is **not** the
validity authority. Future persistent revisions must not silently change this.

## Scope and cost

The original slice applies to format16 readonly retained handles; the bounded
generic extension below adds named catalog formats. Writers and all remaining
profiles retain their existing complete admission. It does not eliminate
row validation or SQL execution work. A warm lease has one snapshot-pinning read
plus journal/query_only/data_version checks and transaction control; it is not a
claim of exactly two SQLite API calls. Independent connections and legacy callers
of read_source still validate live source bytes. Within an exact owned readonly
main-demo view, repeated source snapshots reuse that view's admission rather than
reading/hashing the same source again.

## Generic catalog extension

The same lease protocol also applies to generic storage versions 2, 3 and 4,
including their explicit transaction format11 wrapper, only when activation
issues are empty. Source-bearing application profiles, history format12,
document/register-only profiles and writers are not implicitly included.

Generic admission additionally retains the exact SQLite DDL vocabulary verified
when opening the backend. After a changed epoch it compares that vocabulary as
well as existing catalog/schema/layout/sequence checks, rejecting even a foreign
DDL change whose writer resets schema_version. Database UUID, generation and
activation flags are rechecked on changed/cold admission. This is not a signed
persistent metadata stamp and never grants execution of changed source code.

Within such an admitted readonly view, catalog_schema uses the admitted schema
rather than issuing the same SELECT/JSON decode for each query-planning step.
In-memory schema drift is compared against the detached descriptor before reuse.
Historical schema views and writers retain their original lookup path.

A local diagnostic on a warm format11/base2 COUNT observed 22 statements before
and 8 after this extension: BEGIN; snapshot-pinning sqlite_schema SELECT;
journal_mode, query_only and data_version PRAGMAs; database UUID/generation SELECT;
COUNT; ROLLBACK. This is a statement-count diagnostic, not a latency benchmark or
a claim of two total calls. Cold/changed-epoch admission still performs the
complete checks. The remaining independent snapshot/epoch/identity checks should
not be merged merely to meet a numerical target without proving SQLite ordering
and preserving connection-local ownership.
