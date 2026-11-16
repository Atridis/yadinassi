# Differential persistence of document section payloads

An aggregate document Write still validates and encodes the complete supplied
section inventory, checks the document revision, and validates stored sections
after persistence in the same transaction. It now deletes only obsolete section
identities and UPSERTs declared sections with an update predicate that skips an
exactly unchanged payload. Empty section definitions still remove all payloads.
No persistent cache or schema change is introduced.

The header revision still advances on every successful Write. Tests measure
SQLite total_changes: with one unchanged section, header plus section writes
fall from three changed rows to one; with two sections and only one changed,
from five to two. These are database row-change counts, not timing benchmarks.
Missing/noncanonical section payloads remain replaceable as before; stale
revisions and failed post-validation roll back the entire aggregate. Caller
transactions and lifecycle execution requirements are unchanged.

Focused tests cover unchanged/changed sections, multiple sections, missing and
obsolete inventory, malformed previous payloads, empty definitions, stale writes
and rollback. This is not a native 1C compatibility claim.
