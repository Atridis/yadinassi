# Source XDTO string-only JSON IO

This capability extends the source-owned XDTO scalar/object-tree contract with
explicit-type JSON roundtrips. Zero-argument JSONReader/JSONWriter construction,
reader SetString(text)/Close(), writer SetString()/Close(), and global factory
ReadJSON(reader, type)/WriteJSON(writer, value) are admitted. It adds no file,
stream, callback, serializer-setting, general event API or local-factory grant.
Existing independent JSON services are not broadened by this receiver capability.

Handles belong to the creating source application. Exact canonical code, class,
container, parser/encoder and internal conversion dependencies are checked before
arguments and before work. Host-created, foreign, forged, stale and mutated
handles fail closed. Factory instance overrides of internal conversion methods
are not accepted. Public methods cannot smuggle a file handle into cleanup.

Both directions use candidates. ReadJSON retains the native duplicate-property
scan before map conversion, but does not use generic copy/copyreg dispatch. A new
XDTO graph is validated before publishing reader state, factory accounting and
private object/list/scalar records. Parsing, conversion, schema and quota errors,
including a late admission refusal, preserve the original state. WriteJSON and
writer Close similarly stage their output so failures do not consume the caller's
writer. One document is supported per SetString cycle.

Native bounded semantics are preserved: object/list ownership and exact types,
required properties, nullable values, finite numbers, duplicate-key refusal and
the existing trailing-array-comma rule. Explicit-type null roots retain native
Undefined behavior. No new scalar families, polymorphic type assignment or
external schema resolution are introduced.

Resource ceilings cover input, output expansion, depth, tokens, container entries
and cumulative XDTO allocation. Source JSON handle creation is cumulative and
bounded to 32 per application; discarding or resetting a handle does not refund it.
Application close releases private records and neutralizes retained writer file
slots without invoking an injected object's close method. No legacy VM fallback
or new real-1C parity claim is made.

Scalar descriptor field keys are validated centrally before attribute access,
including the descriptor base. This shared guard protects Create as well as both
XML and JSON readers from forged exact-class descriptors with foreign keys.

Canonical global ReadJSON/WriteJSON services are deliberately refused in ordinary
source execution: they would mutate these native handles outside private state
publication. The refusal follows callable identity rather than spelling, covers
Russian aliases and saved/renamed wrappers, and repeats after argument evaluation
to prevent late implementation swaps. User-defined BSL routines with those names
and standalone/native JSON services keep their existing behavior.
