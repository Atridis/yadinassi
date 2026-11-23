# Typed Query read plans and snapshot validation

The simple catalog scan, relational execution and packages share one typed
binder. The simple path retains its streaming scan executor; package/relational
plans retain bounded materialization and their existing aggregate/result rules.
Unknown fields, wrong parameter types and cross-metadata references fail before
reading. All source families still share one pinned query snapshot.

## Early filtering is conservative

Single physical catalog sources may pass direct field/constant conjunctions to
the backend, retaining the interpreter predicate as a residual check. Documents
may similarly push direct Number, Date and DeletionMark conjunctions through the
owned SQLite projection port. NULL tests, OR, computed predicates, membership,
hierarchy tests and outer joins are not rewritten by this optimization. No
predicate crosses a derived, TOP, grouping or UNION boundary. A predicate with
any unsupported term remains wholly residual: excluding rows must not suppress
an error in another expression.

An equality hidden by a proven `OR FALSE` or `AND TRUE` in `JOIN ON`
can use the same hash join as the bare equality. Newly exposed hash keys
are used only if the remaining condition cannot raise: key pruning must not
make an error on a rejected or NULL pair disappear. Actual alternatives and
SQL UNKNOWN are not treated as Boolean identity terms.

## Integrity is not a filter

The first scan still validates the complete bounded source, including values
excluded by WHERE and unprojected document sections. Only successful validation
is reusable, within the same read-only view. No marker survives the view or is
accepted from a third-party backend. Write views do not reuse these markers.
Repeated source occurrences avoid repeating the integrity pass, not the required
logical reads. All reference identities and source limits remain checked.

SQLite document projections return separate value rows, never partial cards.
After the first complete validation, header-only reports do not rematerialize
sections; standard-field-only reports do not fetch the JSON payload again.
Section reports only materialize the selected section. The Query adapter charges
all original document cells/text on each source occurrence, including hidden
sections and filtered-out owners, before exposing results. Thus narrow projection
and TOP cannot evade the input budget. Other backends retain the complete-card
fallback and its full validation. This is a local host contract, not additional
native parity evidence.

## Structural counts on the owned SQLite query port

The flat catalog `COUNT(*)` data path does not materialize or validate
unprojected payloads. This includes a non-distinct `COUNT(Ref)` of the
non-null physical row identity, row-independent WHERE conditions, inert
constant companion projections, closed Decimal arithmetic around COUNT, and
ORDER BY an already-evaluated projected expression. A known false or unknown
WHERE selects no input while the same native count still charges the existing
input-row/cell budget. An admitted one-row aggregate result keeps its original
bound column descriptors. The bare count keeps its structural SQLite count;
normalized forms prove canonical, nonzero physical UUID keys in the same SQL
statement. Unusual physical spellings fall back to the existing UUID decoder
and logical duplicate check, so a valid alias is not rejected or a bad key
counted. This does not check unrelated payload corruption.

There is also a full-source SQL proof for flat catalog and document headers.
It can count a distinct physical `Ref` or apply an exact Boolean equality on
`DeletionMark` without materializing rows. The proof checks unselected
headers and their original input budgets; if it cannot establish them, the
original reader decides the result or error. A tabular part's `Ref` names
its owner, not a unique row, so distinct owner counting remains residual.
Other DISTINCT keys, nullable inputs, and richer filters are not inferred.
Explicit writers and raw storage readers retain their existing paths.

On owned SQLite document reads, the same closed COUNT expressions can also
count a header source or a document tabular part in one statement. This path
proves the whole document source, including hidden fields and sibling parts,
and charges its original cell, text, row and physical byte budgets. The
witness covers canonical keys, typed scalar fields, stored posting status,
applicable catalog-reference presence and part line order. Unproved data
(including non-ASCII text) falls back to the original reader rather than
changing what it accepts or which error it reports.

## Equivalent CASE arms in an ordered page

An unfiltered ordered `TOP` over a flat catalog can project identical bound
scalar `CASE` arms without evaluating conditions that cannot raise. One
SQLite statement checks the full source and the original pre-TOP cell and
text budgets, then returns the bounded page in the original order. Only
non-numeric arms and data the same header proof can validate use this path;
unknown data, unproved expressions and other source shapes use the original
executor. For example, a division that can fail outside the selected page
must still be evaluated by that executor.

## Paging and explicit indexes

SQL catalog continuations carry the last lexicographic sort key rather than an
OFFSET. The exact versioned Decimal/casefold/UUID comparators, each direction,
logical UUID tie-break and physical rowid tie-break are retained. Tokens remain
single-use and bound to the view, predicate, order and projection. Legacy JSON
and hierarchical fallback scans remain bounded Python materializations; they do
not acquire an artificial SQL seek implementation. Document scans retain their
single owned streaming cursor.

`sqlite_query_indexes` supplies a canonical default UUID-order index per mapped
catalog and registers comparators on ordinary read/write/create connections.
It never executes DDL. Actual installation and admission must come through the
explicit versioned migration planner. Until that integration is present, these
specifications alone do not mean databases have indexes. This fixed index does
not promise acceleration for every custom field or arbitrary ORDER BY.
