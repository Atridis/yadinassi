# Direct source ValueStorage snapshots

Source execution, source object handlers and source forms admit the exact bilingual
ValueStorage constructor with one argument. It captures a bounded immutable
snapshot before publishing the value. Existing snapshot node/depth/text/binary and
numeric budgets, source persistence codec, transactions and session type checks
remain authoritative. No native storage format or new database permission is added.
The standalone direct constructor inventory is unchanged.

The source-only capture profile accepts generated lists, structures and typed maps.
Map entry tokens are checked without extension-object callbacks; canonical key
collisions reject rather than silently overwrite. Cycles reject, and shared
children are copied per occurrence under the existing budgets. This map extension
also applies to the already opt-in source temporary-storage accounting path; the
original map observation now replays without changing its expected output.
Default capture still rejects direct representation objects.

The constructor deliberately does not admit compression arguments or nested
ValueStorage values in this slice. Nested storage is refused before its Get or
restore method can run. That constructor-only limit does not alter default capture
or existing temporary-storage nested-value behavior.

Source Get/Получить currently exposes only plain Undefined, Null, Boolean, Number
and String snapshots. It validates exact immutable snapshot fields, factory and
method hooks before canonical restoration. Collection, compressed and other tags
are explicitly refused at this method boundary. Existing host Get and persistence
code still restore their canonical supported values and remain unchanged.

Saved source methods retain the same snapshot and activation checks. Unknown
members, patched factories/hooks, modified snapshots and malformed private fields
fail closed. Source-scoped constructor lowering supplies argument count before
argument expressions, allowing bounded constructors to reject invalid arity early.
Tests cover source constant handlers, session snapshot isolation, forms, per-get
independence, typed-map collisions, quotas/cycles, tampering and lifetime VM poison.
