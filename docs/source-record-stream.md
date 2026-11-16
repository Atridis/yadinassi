# Incremental source record decoding

Catalog and document selections now decode each SQLite cursor row immediately,
instead of first fetching every raw payload into a separate list. The public
result remains a complete list; no partial result is exposed if a later row
fails. Section-profile reads inherit the document path.

The preflight database, aggregate byte and record-count guards remain. The SQL
LIMIT and an independent per-query counter remain, as do UUID/revision,
canonical payload and code/number consistency checks. Snapshot ownership,
ordering, missing point-read errors and outer-transaction failure rollback are
unchanged. Decoded values still occupy space in the final result; the change
removes the additional whole-selection raw-payload list, not all result memory.

Tests prohibit fetchall for the targeted selection, verify fetch/decode
interleaving and cover late corruption, cursor failure, count bounds and missing
point reads for both record families. No measured timing or native 1C parity
claim is made.

The cursor is closed in a finally block, including early decode and count-bound
failures. A retained exception traceback must not keep an unfinished SQLite
statement and reader lock alive; regression tests keep that traceback while a
second connection commits successfully with timeout zero.
The same deterministic retirement also covers scoped and whole-store section
payload streams, so later section-validation failures cannot leave a statement
alive through a retained traceback either.
