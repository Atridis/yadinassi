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
