# SQL-first query planning: contracts and first vertical slice

## Target architecture

The target is **1C query AST → bound typed logical plan → provider physical plan
→ SQL execution → typed BSL result**, not a Python relational engine with a
permanent collection of benchmark exceptions. The existing `_scan_sql` already
pushes admitted WHERE/ORDER work down. Aggregation and joins are the next physical
operators. `query_pushdown` is the initial explicit selection seam; the current
Python executor remains a named residual implementation and differential oracle
until a provider proves the semantics of each operator.

Three independent proofs must not be conflated:

1. An immutable verified schema/descriptor binds logical identities, field types,
   qualifiers, access and private physical names. A generation number alone is
   not a database revision protocol; current generation 1 does not prove freshness.
2. Snapshot data admission validates bounded physical rows and their logical
   identities. Metadata receipts cannot certify row values or UUID uniqueness.
3. The physical plan proves operator semantics for its exact typed shape. SQL
   syntax similarity alone does not prove NULL, Decimal, collation, empty-group,
   duplicate, error, or resource-bound equivalence.

Provider-facing plans use closed typed requests and bound parameters, never BSL
SQL fragments or caller-controlled table identifiers. SQL templates derive names
only from verified layout/schema maps. Unsupported shapes return an explicit
capability decline before execution; integrity/access/schema failures are errors,
never a reason to silently fall back and conceal corruption.

## Implemented first operator

`CatalogAggregateRequest(count_all_v1)` represents only one complete catalog's
COUNT(*). The selector rejects predicates, groups, HAVING, ordering, DISTINCT,
joins, sections, derived/external/temporary sources and INTO.
The backend may decline old storage, hierarchy or write-transaction shapes.
Normal binding still validates names, output schema and access. The resulting
single value is exact Decimal with the previous BSLQueryResult columns and TOP
behavior. An empty input produces one zero row. Duplicate *payload* values and
NULL reference fields remain rows, not a COUNT(field) reinterpretation.

SQLite executes the existing full-source scalar admission first. This validates
all fields, even ones COUNT does not project. It retains existing bounded input
checks before payload reads. A TEXT record-id primary key does **not** prove
logical UUID uniqueness: differently spelled identifiers can normalize to the
same UUID. A separate SQL `COUNT(DISTINCT record_id COLLATE yadinassi_uuid_v1)`
proof must equal COUNT(*), using the same UUID normalization as the old seen-set.
Malformed IDs, zero UUIDs and oversized encodings fail during scalar admission.
This is why raw COUNT(*) or an existing scalar proof alone was rejected.

After successful admission the immutable count proof is retained only through
the existing actual-read-connection ReadHandle. Its pinned snapshot epoch is
checked before reuse; external data-version change and internal writer paths
invalidate proofs. The proof is never copied by file path/generation, promoted
using a data_version read after rollback, or treated as schema authority.
Cold reads still validate the complete source. Warm reads avoid row decoding and
DISTINCT work, but execute SQL COUNT(*) and verify it against the pinned count.
The old Query MAX_ROWS/cell/text accounting is applied despite avoiding Python
row materialization. Physical budget failures remain errors, not larger results.

## Expansion path, not blanket SQL translation

Next extend the typed capability to projection/filter/order and compatible
aggregate/group operators, composing proven nodes. Share source admission once
per snapshot rather than re-running it for every expression. COUNT(field),
COUNT(DISTINCT), SUM/AVG/MIN/MAX each need their own NULL/type/precision contract;
The owner explicitly accepts Decimal precision loss in SQL calculations as a
DBMS-dependent design tradeoff. Therefore SUM/AVG and arithmetic may use provider
numeric execution with a documented result precision/range policy; exact Decimal
parity is not an admission prerequisite. Test and report boundary differences,
overflow/NULL behavior and coercions rather than disguising them. Stored Decimal
values and their write/read precision must not change as a side effect. ASCII
NOCASE and NULL/type semantics still require their own independent decisions.

Reference dereferencing and tabular sections lower to typed joins with cardinality
and ownership constraints. Virtual tables lower to provider subqueries/joins,
not textual replacements. In particular SliceLast's parameter filter acts
before choosing the last record, while an outer WHERE acts afterward: these are
different nodes, and predicate movement must prove that it preserves meaning.
Public 1C descriptions motivating these boundaries:
- https://kb.1ci.com/1C_Enterprise_Platform/FAQ/Development/Queries/Query_language/#Using_filters_in_queries_with_virtual_tables
- https://kb.1ci.com/1C_Enterprise_Platform/Tutorials/Practical_developer_guide_8.3/Lesson_13._Reports/Theory._Virtual_query_tables/

The initial tests are canonical-contract/differential evidence, not new native
observations. No native expected data changed. No performance numbers are claimed
before isolated cold/warm measurement; the supplied audit timings are hypotheses.

The official 1C implementation describes a DBMS-independent intermediate query
language (SDBL) followed by provider SQL generation. That is architectural
inspiration, not an instruction to reproduce proprietary storage:
https://1c-dn.com/blog/working-with-diverse-dbmss-in-1c-how-we-do-it-without-losing-our-minds-or-calling-the-developers/
Reference dot-access is modeled with LEFT JOIN and shared traversal nodes;
composite-reference branches need explicit discrimination, not arbitrary joins:
https://1c-dn.com/library/accessing_fields_from_other_fields_using_dot/
ISNULL must preserve the first argument's declared type/coercion behavior; raw
COALESCE is not automatically equivalent. 1C documents expression/aggregate precision rules; use these as evidence when
choosing and reporting provider result descriptors, not as a reason to reject
the owner's accepted SQL calculation precision tradeoff:
https://1c-dn.com/library/bitness_of_results_of_expressions_and_aggregate_functions_in_query_language/

The current SQLite backend explicitly rejects WAL storage. This COUNT slice
preserves that admission boundary; its tests check rejection rather than silently
adding a new journal/snapshot model. Foreign commits before pinning and after
rollback are exercised within the supported rollback-journal contract.

TOP 0 remains an existing parser rejection (empty and nonempty sources alike).
Explicit transaction read leases decline this first physical shape and retain
staged-write visibility through the existing relational executor. This is a
scoped initial limitation, not a permanent SQL-first architecture boundary.

## Enum-bound MainDemo end-to-end capability

A format16 MainDemo catalog COUNT does not itself aggregate enums, even though
its plan always carries an enum binding. That binding is no longer a blanket
reason to decline COUNT. The existing `execute_report` / `read_snapshot` ownership
witness remains in place, and the exact binding validates its live owner and
canonical namespace mappings before and after provider execution inside that
same witness. Unused enum parameters still undergo their prior ownership checks.
The report's DocumentView forwards only the typed aggregate request to its
existing catalog view, acquiring no second connection or independent snapshot.
Transactions still decline this physical path and execute the explicit current
relational plan, retaining staged data visibility; there is no legacy VM fallback.

Tests exercise actual MainDemo `BSLQuery.Execute`, BSL `Query.Execute` and batches
with Python materialization disabled, not just the lower-level provider method.
They verify same-snapshot readonly authority, revoked/mutated enum owners,
foreign enum parameters, corrupted unused enum/reference fields and altered
source content. The prior generic benchmark does not establish MainDemo speedup
or format16 admission benefits; those require a new actual-profile measurement.
The accepted SQL numeric precision tradeoff is our provider policy, not a claim
that all native 1C arithmetic or SUM operations are approximate.
