# Ordinary XML workflow measurement

`xml-workflow-family-v1` is one coherent 33-case batch. It measures actual
server/client observations and compares the same source with the interpreter;
it does not encode presumed native semantic answers.

## Primary specification

Signatures and availability were checked against the official EDT archive
`com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`, SHA256
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Source pages are under `nl/en/html/SyntaxHelperContext/objects/`:
`catalog63/catalog565/XMLReader`, `XMLWriter`, and
`catalog2/catalog613/XMLNodeType`.

Important distinctions: `Skip` is a procedure; `WriteCurrent` writes the current
reader node without advancing it; `Close` returns an empty string for file
writers; `OpenFile` supports an explicit BOM flag; `WriteRaw` is specified as
unprocessed XML. This batch supplies only a valid bounded raw fragment, not a
DTD or external-resource reference.

## Cases

1–12: element/text/end token sequence, indexed and named attributes, namespaced
attributes, prefixed/default namespaces, attribute iteration, first/next,
subtree skip, MoveToContent, predefined/character entities, CDATA/comment/PI,
and EOF. MoveToContent also observes the default IgnoreWhitespace and changes
it during reading; entity reading uses explicit default XMLReaderSettings.

13–26: empty/nonempty elements, text/attribute escaping, incremental attributes,
nesting with explicit no-indent writer settings, default/explicit encoding declarations, CDATA/comments/PI,
namespace mappings and namespaced attributes, prefix lookup, valid raw fragment,
and current-node reader-to-writer copying.

27–29: UTF-8 with BOM, UTF-16 with BOM and UTF-8 without BOM file roundtrips,
including attribute/text content and the file-writer Close return value.

30–33: reader/writer reuse, object/token/settings type identities, malformed XML and
ordinary invalid attribute-write ordering.

All file cases allocate a unique temporary root, reject a pre-existing path,
then operate on the literal owned `a.xml` beneath it. Close and exact cleanup
run on success and failure paths. The root is deleted only after checking it
is empty; unexpected children are not recursively swept. Tests put allocations
inside an outer `TemporaryDirectory`. No real user files, URL resources,
permissions/attributes or security settings are accessed or changed.

## Closed observer and integration

Two calibration records precede 33 ordered observations. Each successful value
is encoded as a length and UTF-16 hexadecimal units. Strings are bounded to
56 units; the worst-case rectangular output is 8003 bytes within the existing
8192-byte cap. Action and observer failures remain distinct. Expected-error
cases report a successful short observation only when the BSL exception handler
actually runs. Every ordinary case must be observable for availability;
availability is separate from byte-exact native/interpreter equivalence.

The profile reuses existing reviewed host/bootstrap/emitter/client capture,
source binding, provenance, process cleanup and workflow routes. No new trigger,
permission, credential or image is introduced, and no resource cap is raised.

`!todo` marks DTD/schema/XDTO/stream support and rare lexical/namespace corners.
External entity processing must remain disabled regardless of these deferrals.

## Evidence status

Native execution is pending. Local synthetic observations, isolated replay,
and contract tests are **not** real-platform evidence. Do not claim native
parity without a source-bound native capture and independent artifact audit.
