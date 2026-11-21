# Source XDTO string-only XML IO

The subsequent [string-only JSON capability](direct-source-xdto-json-strings.md)
adds explicit-type JSON roundtrips. JSON exclusions below describe this original
XML slice. Neither capability grants generic file or stream IO.

This is a bounded XDTO roundtrip capability, not general XML or filesystem access.
The source application may create zero-argument XMLReader/XMLWriter values.
Reader SetString(text) and Close(), writer SetString() and Close(), and the global
factory's ReadXML(reader, explicitType) and
WriteXML(writer, value, explicitName, explicitURI) are admitted. Method aliases
remain bilingual. Settings, implicit root/type selection, streams, files, general
XML event APIs and XDTO JSON codecs remain unsupported. Existing independent
JSON-service capabilities are neither expanded nor revoked by this slice.

Only readers/writers created by the same source application's guarded path are
accepted. Exact classes, fields, nested state and canonical code bindings are
verified against independent application-owned records, before argument effects
and again before execution. Host-created, forged, foreign and closed-application
handles fail closed. Saved methods revalidate ownership and contracts.

A writer accepts one XDTO document per SetString cycle. A reader accepts one
complete XDTO read per SetString cycle. Reset starts a new string session. Graph
admission is the existing global factory scalar/object-tree contract, including
acyclic package models, exact types and bounded lists. It does not admit new
scalar families, settings, schema resolution or polymorphic xsi:type behavior.

WriteXML formats into a candidate string writer without generic deepcopy and
publishes the destination only after validation. ReadXML uses a candidate reader
and stages the newly produced object/list/scalar graph. Failed parsing,
conversion, required-property checks, quota checks or source admission do not
publish candidate reader/writer state or partial graph records. Allocation
counters are rolled back on a rejected read, including fail-closed admission.
Pre-existing object state is checked before reading or writing.

XML parser DTD/external entity refusals remain in force. Active resource limits
and their imported aliases are validated before use; string bytes, escaped output,
XML depth/nodes and cumulative XDTO allocations remain bounded. There is no file
or network resolver and no VM fallback. Native default IO behavior is retained;
this source-only staging path does not claim new real-1C parity.

Each application has a cumulative limit of 32 source-created XML handles; closing
or discarding a handle does not refund creation quota. Application close releases
private records and neutralizes retained writers through the original instance
dictionary descriptor, without closing an injected foreign stream. Failed writer
Close is also staged, allowing a retry after a temporary quota restriction is
removed. Generic Python copy/deepcopy dispatch is not used on the source path.
