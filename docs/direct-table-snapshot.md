# Current direct tables in host ValueStorage

The snapshot codec now reads the current column `_items` list and positional
row storage rather than requiring historical mutable `columns.items`/`cells`
containers. It verifies exact storage/schema/row/column owners and schema shape,
and keeps the existing scalar descriptor, payload, depth and size checks.

Direct index tuples are captured as the existing immutable offset definitions.
They must be sorted, unique, nonempty, in range and consistent with the table's
declarations. Restore uses the current Indexes.Add API after reconstructing the
validated rows; no cache is read, serialized or warmed. Historical empty or
repeated-column index definitions are explicitly rejected rather than silently
normalized into a different index.

This is a codec-only adaptation for host ValueStorage, including tables created
by default BSL and handed to the host. It does not change table runtime/coercion,
add legacy index APIs, or relax the source-owned ValueStorage.Get scalar-only
boundary. Already conformant typed values round-trip; unqualified values still
fail capture, and future row writes retain current lightweight semantics.

Focused checks cover untyped/conformant typed roundtrip, owner independence,
lazy cache state, live restored rows, post-restore invalidation, ignored hostile
cache objects, malformed storage/index fields, and existing hostile descriptor
and malformed snapshot rejection. This does not claim all historical typed
ValueStorage tests pass: coercion, old index objects and column move semantics
remain separate unsupported contracts.

Source sealing includes the three newly inspected exact storage classes and
slot descriptors (Schema, TableStorage, SearchIndexes). Capture uses bounded
codec-local schema validation, not a new Schema.validate method dispatch.
Declaration counts/positions are bounded before traversing their elements.
Snapshot column names already require Structure-style identifiers, excluding
commas; restore's current Add argument cannot reinterpret a valid saved name.
