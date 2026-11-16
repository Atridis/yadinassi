# Whole-store section validation across document families

Full record validation reads section payloads in one ordered bounded stream
instead of one query per populated document family. Point/selection reads still
use their existing scoped query. Both paths share the payload validator.

The global stream is bounded to 160001 rows and rejects row 160001. Each family
and record must belong to the validated header inventory, every declared section
must be present exactly once, and byte, row, canonical-payload and foreign-key
checks remain. Families with no payload rows are also checked for missing
sections. No persistent cache, write path, profile or authority change occurs.

SQL trace tests demonstrate eight families using one payload query, plus
missing/foreign/corrupt later-family cases. Existing one-family, reopen, empty
schema and caller-transaction tests remain. This is a query-count improvement,
not a measured wall-clock speedup or native 1C compatibility claim.
