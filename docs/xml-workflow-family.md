# Ordinary XML reader/writer workflow

Status: the source-bound XML33 batch was acquired on real 1C 8.3.27.1508
(client and server identical). Five ordinary differences were corrected and the
local runtime now replays all 33 captured observations exactly. The original
failed-runtime report is preserved unchanged; final exact-head CI is pending.

## Covered workflow

- `XMLReader / ЧтениеXML`: string and bounded regular-file sources, `Read`,
  `Skip`, `MoveToContent`, current node/name/local name/prefix/namespace/value,
  attribute count/index/name/namespace lookup and attribute iteration, close/reuse.
- `XMLNamespaceContext / КонтекстПространствИменXML`: current scope, default
  namespace, depth, prefix/URI lookup and detached arrays/map of bindings.
- `XMLWriter / ЗаписьXML`: string/file targets; XML declaration, elements,
  ordinary and incremental attributes, text escaping, namespace mappings,
  comments, CDATA, processing instructions, current-reader-node copying without
  moving the reader, close/reuse. `WriteRaw` accepts only a bounded validated
  fragment, not native unchecked malformed markup.
- Basic `XMLReaderSettings / ПараметрыЧтенияXML` and
  `XMLWriterSettings / ПараметрыЗаписиXML`; ordinary XML 1.0,
  `XMLNodeType`, `XMLSpace`, and `XMLValidationType.NoValidate` identities.
- UTF-8/UTF-16 and supported explicit local text codecs reuse FileIO's regular
  descriptor checks; writer BOM selection. Reader snapshots immediately close
  their input descriptor. The writer closes its output descriptor on completion.

Settings and namespace context expose only explicit bilingual BSL members;
Python parser objects, reflection, host attributes and stream handles are not
exposed. Type identities use additive registrations. Internal serialization of
these types is explicitly unsupported rather than given invented platform GUIDs.

## Resource/security boundary

Reader input is at most 16 MiB (UTF-8 bytes for string sources), depth 256,
100,000 event nodes and 100,000 attributes across the document, and 1,000,000
cumulative namespace bindings. Writer budgets are 1,000,000 characters after
escaping/rendering, depth 128 and 100,000 nodes including attributes. These are
local execution limits, not claims about 1C limits.

DTD declarations, custom/entity declarations, parameter entities and external
entity resolution are refused. No external file or network resource is resolved,
even when a settings flag requests ignoring a DTD. Standard XML character/entity
references (`&amp;`, numeric references, etc.) remain supported. File access is
explicit and uses existing local regular-file guards; no device, URL, recursive
cleanup or permission changes are introduced.

The native batch creates an owned temporary fixture root and uses only its fixed
fixture files. Cleanup never deletes unexpected children. Paths are tested by
relationships; no personal paths or file contents are captured.

## Deferred (`!todo` in code)

DOM, XDTO, schema validation, DTD declaration iteration, `XMLAttributeType`,
custom entities, streams, XML 1.1, complete Unicode XML name ranges, exact
malformed-input cursor timing, exotic codec behavior and unchecked raw markup
are not implemented. Reader eagerly builds a bounded token snapshot on its first
read. Native XML33 establishes its ordinary token/default/indentation cases only;
advanced whitespace, namespace, mixed-content indentation and lifecycle corners
still require later evidence rather than inferred universal equivalence.

## Primary documentation and measurement

Implementation was checked against the official 1C EDT documentation archive:
`com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar`, distributed with
[EDT 2026.2](https://edt.1c.ru/downloads/releases/ruby/2026.2/plugins/com._1c.g5.v8.dt.platform.doc_3.0.1.v202610261959.jar).
Archive SHA-256:
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
Only ZIP HTML entries were read; the JAR was not executed.

The source entries under
`nl/{en,ru}/html/SyntaxHelperContext/objects/catalog63/catalog565/` document
`XMLReader`, `XMLWriter`, both settings and `XMLNamespaceContext`; enum entries
are under `catalog2`. In particular, `WriteCurrent` does not advance the reader,
`Skip` is a procedure, attribute lookup supports index/full name/local name+URI,
and `Close` returns the string target or an empty string for a file target.

See [the single 33-case measurement contract](xml-workflow-family-measurement.md).
The archived acquisition passed 50 source/provenance/capture/cleanup checks;
see the measurement document for identities and remaining evidence limits.
