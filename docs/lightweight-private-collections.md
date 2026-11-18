# Direct private data collection compilation

Extend the existing module scalar/array/map dataflow to fresh ValueTable and
ValueList, columns, rows and items. This is a normal compile-time choice within
the single compiler, not a selector, interpreter fallback, runtime replay, or a
benchmark-specific source match. Literal values, aliases, branches, loops and
several collection families can be combined. Unsupported effects remain on the
existing external-boundary route.

The grammar reads no opaque incoming values, invokes no user services, imports,
Execute/Eval or host callbacks, and never publishes intermediate locals. Every
collection originates from a generated native constructor. Such data cannot be a
foreign/privileged database receiver. Row values are generated primitive data.
Generated code calls the actual native add/get/set/column methods directly. It
does not invoke service/member resolution, module graph validation or authority
scan per cell. Native growth limits remain in real allocating methods. Canonical
classes and their Python implementation are trusted internal code, not a public
monkeypatch/constructor-service override API for this route.

The public execution entry and final publication boundaries remain unchanged.
Close/revoke during computation cannot publish new data; overwriting previous
public bindings still checks after each write. Existing published collections,
external inputs and escapes are not eligible. This does not make the complete
language callback-free and does not grant raw native access to external objects.

Functional compatibility (ordering, coercion, schema, errors) follows the current
lightweight native classes, not the old interpreter. No universal 2–3× claim is
made; run the identical actual API matrix including preparation, slow external
cases and raw Python before judging this implementation.
