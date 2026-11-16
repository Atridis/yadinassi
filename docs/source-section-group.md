# Bounded source section grouping

The explicit source document section profile admits `GroupBy/Свернуть(groups,
totals)` on the owned in-memory buffer. The totals argument can be omitted.
Both lists are explicit comma-separated field names (empty means no columns).
Grouping and total fields must be disjoint and together cover the complete
section schema. Omitted-field defaults and reference/enum grouping are not yet
supported. Keys are scalar Boolean, Number, String or Date; total fields must
be Number. Names are case-insensitive, without whitespace or duplicates.

The operation copies a complete, typed bounded section snapshot to the existing
ValueTable grouping engine. Its scalar equality, ordering, precision limits and
qualified numeric adjustment remain in effect. Every resulting value and the
complete owner buffer budget are validated before replacement. Failure leaves
original rows and handles intact. Success replaces rows, invalidates old handles
and active iterators, and assigns new line numbers. It neither writes the DB nor
runs lifecycle callbacks. Explicit Write is still necessary. Existing caller,
transaction, safe-mode and detached-owner restrictions are unchanged.

This is source-host evidence, not new native section parity. In particular,
identity/liveness of row handles across native section grouping is not claimed.
