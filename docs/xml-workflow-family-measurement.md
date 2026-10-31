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

Real 1C 8.3.27.1508 Linux acquisition: GitHub run `41227374058`, attempt 1,
job `124614250280`, PR #171 head `fa36ac4e80ba3d7a4f720011eaec7bb7a274059f`.
Synthetic merge `e2d02cc66f98de7aefa3c6eccd3633fad59df017`, ordered parents
`bc272346ed2062b185017214eebae5928df1a79e` and the feature head, tree
`a4132279a2fdb0344d6be7525524c4c030cdad24`.

Native source SHA256:
`403ae0f300e5a07fe3c78dff32148f96f7de667ed3b3e0720b8fad3afe454f92`.
Client and server captures are identical, 35 messages / 2497 bytes:
`07c4ee0a14ce53f0929bb2c41caf9d9c5dc5fdcc2fec68d5bb28f21874759f0c`.
Archived provenance SHA256:
`351a270111cac9fc8bb2ee144ae1d260b30b69a16b7c28af9536449bb61be8fc`.
The immutable capture/provenance are under `tests/fixtures/xml_workflow_family`.

The original runtime had five mismatches; its report remains rejected and is
not relabeled as a pass. Measured corrections:

- 01: text node `Name` is `#text`.
- 08: `Skip` stops at the skipped element's end token.
- 11: an XMLReader source with omitted settings uses legacy defaults that treat
  CDATA as text and ignore comments (explicit settings retain documented defaults).
- 20: default indentation includes CDATA/comment child lines.
- 25: raw insertion has no added leading indentation, but the parent closing tag
  still receives its ordinary line break.

The corrected runtime replays **all 33** immutable observations exactly, without
changing the native source, filtering cases or relaxing comparison rules.
`tests/test_xml_workflow_native.py` verifies the immutable acquisition and exact
replay. Final corrected-head CI remains a separate gate.

Acquisition audit: 50 checks cover archive digest/membership, report/provenance
identity, ordered merge/source tree, runtime85 inventory, dependencies, all22
staged inputs and9host inputs, regenerated client/server modules, nonce/lifecycle,
process census, cleanup, availability and original bounded-child mismatch replay.
Original transport envelope was not archived: strict envelope validation was
rerun on a reconstructed envelope from byte-verified report/provenance/capture.
This is not a claim of possession of the original transport bytes. Existing
bootstrap security-settings observations are inherited from the authorized
harness; this feature adds no security setting changes.
