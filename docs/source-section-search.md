# Typed source section search

The explicit source-document-section profile admits `Find/Найти(value, field)`
and `FindRows/НайтиСтроки(structure)` over the current owned memory buffer.
This fills the section lookup gap without converting it to a detached table.

Find requires one explicit field, returns the first matching live row in current
order, or Undefined. Implicit all-column and multi-column Find are not admitted.
FindRows accepts an exact Structure, combines typed predicates with AND, and
returns a detached Array of live row handles in current order. An empty Structure
returns an empty Array, matching the existing bounded ValueTable contract.
Membership is a snapshot; subsequent value changes do not recalculate the Array,
and deleted or invalidated handles remain unusable.

Fields and predicate values are validated even for an empty section. Values use
the existing exact source field codec (including owner/domain-bound references),
then BSL equality, with no coercion. Encountering an unassigned selected field
fails rather than inventing a default. Search scans are bounded by the existing
whole-owner section budget. Find short-circuits on its first match; FindRows
validates the visited selected fields and returns no partial result on error.

No query grants, schema changes, handlers, writes or iterator invalidation are
introduced. This is a bounded source-host contract, not new native parity.
