# UserMessage: structured local delivery

`СообщениеПользователю / UserMessage` is a documentation-based local runtime
increment for field and row validation messages. It is **not native-parity
verification**, automatic ObjectModule execution, a managed-form renderer, or
permission to activate previously rejected configuration modules.

## BSL surface

- `New UserMessage` / `Новый СообщениеПользователю()` constructs an empty message.
- Read/write Text/Текст, Field/Поле and DataPath/ПутьКДанным are strings.
- Read/write DataKey/КлючДанных accepts a supported catalog reference or Undefined.
- Read/write TargetID/ИдентификаторНазначения accepts UUID or Undefined.
- `Message()` / `Сообщить()` emits a snapshot; it is a procedure with no arguments.
- `SetData(Object)` / `УстановитьДанные(Объект)` accepts an existing supported
  CatalogObject, takes its detached Ref and looks up an explicitly host-bound form
  attribute path for that exact instance. It does not read/write the database.
- Type/TypeOf and dynamic New work with both type aliases. Names are case-insensitive.

Text/Field/DataPath start empty; DataKey/TargetID start Undefined. Repeated Message
calls produce separate records using the current properties. Properties are not
cleared by delivery. Setter/SetData validation precedes mutation, so an error
retains the previous property pair. These defaults, repeated-call behavior and
failure behavior are explicit local choices pending native measurement.

String values remain unchanged, including punctuation, Unicode and row paths
such as `Object.Warehouses[0].Warehouse`. Paths are inert text, not evaluated BSL,
filesystem paths, or instructions to navigate. Strict string types and local
limits (65,536 characters for Text; 4,096 for Field and DataPath) reject oversized
or non-string assignments without implicit conversion. These limits are not
claimed as platform limits.

## Host delivery and future UI connection

`Interpreter(output=..., user_message_sink=callback)` sends `UserMessageRecord`
values to the trusted Python callback. Without a structured sink, it sends only
Text through the existing output callback, so CLI and existing FormSession plain
messages remain usable. An installed sink replaces that fallback, not duplicates
it. `interpreter.user_messages.set_sink(callback_or_none)` can select delivery
from an existing host, including a FormSession's interpreter.

A record has text, field, data_path, data_key and target_id. Its properties are a
frozen snapshot. DataKey preserves the existing runtime reference identity and
callbacks; this is **not a JSON/wire DTO, deep-frozen object graph, authorization
token, or permission to open another database/form**. A future UI adapter must
validate its own database/session scope and map the reference to its finite
protocol before rendering/navigation. No Python callbacks or reference internals
are exposed through the BSL message object.

`interpreter.user_messages.bind_data(catalog_object, "Object")` and
`unbind_data(catalog_object)` are explicit host-only mapping operations. Mappings
are weak and instance-based. A different detached object with the same reference
does not inherit the mapping. Unmapped objects use an empty DataPath. A failed
SetData leaves both DataKey and DataPath unchanged. Existing standalone ThisObject
is not silently reinterpreted as an object-module receiver.

Logical server/NoContext activations and imported modules share their execution
family's message context. Separate root interpreters remain isolated. Delivery is
synchronous to the host; no native client/server deferred-message queue, automatic
transaction rollback, focus movement, window opening or UI highlighting is added.
An exception from the sink propagates without retry. The host owns storage,
backpressure, context lifetimes and any later event-level delivery policy.

## Evidence and limits

The official [messages guide](https://1c-dn.com/library/messages_displayed_to_users/)
explains Text/Field, object-instance-to-form-attribute mappings, DataPath/DataKey,
and zero-based row paths. The published syntax reference documents
[SetData](https://yellow-erp.com/help/sh/objects/catalog63/UserMessage/methods/SetData3549.html),
[DataKey](https://yellow-erp.com/help/sh/objects/catalog63/UserMessage/properties/DataKey6964.html),
and [TargetID](https://yellow-erp.com/help/sh/objects/catalog63/UserMessage/properties/TargetID9247.html).
Documentation informs this implementation; no 1C observation has been acquired.

Document/register objects and record keys, other SetData argument families,
GetUserMessages/native queue semantics, the BSL form-mapping global, native GUI
association and TargetID routing are not implemented. TargetID is retained as
metadata only. ObjectModule activation, automatic BeforeWrite invocation,
form-data conversion and exported object-method dispatch remain separately gated.
String presentation, internal serialization of the message or its Type,
TypeDescription cells, ValueIsFilled and passing message objects across logical
client/server calls are not claimed. A message created and sent on the server is
supported; transferring that object as a parameter is a different unsupported step.

The new runtime source increases the exact provenance inventory from 121 to 122
files. Tests update only that count; all aggregate hashing, source drift checks,
512-file limits and native acquisition gates remain intact.
