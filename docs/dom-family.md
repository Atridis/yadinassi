# Bounded ordinary XML DOM workflow

This family adds a mutable XML tree, not another streaming-XML alias. The local
checkpoint supports constructing a document, reading through `XMLReader`,
navigating and editing nodes/attributes, cloning/importing subtrees, and writing
through `XMLWriter` to its existing string or explicitly opened file target.
Native 1C calibration is **pending**; local tests are not platform observations.

## Public surface

- `DOMDocument / ДокументDOM(uri, qualifiedName)`, `DOMBuilder / ПостроительDOM`,
  `DOMWriter / ЗаписьDOM`, `DOMNodeType / ТипУзлаDOM`.
- Returned Element, Attribute, Text, CDATASection, Comment,
  ProcessingInstruction, DocumentFragment, NodeList, ElementList and AttributeMap
  types have explicit `Type`/`TypeOf` identities. They are not arbitrary factories.
- Document `CreateElement`, `CreateAttribute` (name or URI/name), `CreateTextNode`,
  `CreateComment`, `CreateCDATASection`, `CreateProcessingInstruction`,
  `CreateDocumentFragment`, `ImportNode`, `GetElementByTagName`.
- Child append/insert/replace/remove, parent/sibling/owner references,
  `ChildNodes`, `HasChildNodes`, `HasAttributes`, `CloneNode`, `Normalize`,
  `IsSameNode`, `IsEqualNode`, `TextContent` and ordinary node/name/namespace fields.
- Attribute get/set/remove, attribute-node attach/detach, named and indexed
  AttributeMap operations. Collections provide `Count`, `Item`, indexing and
  iteration; queries and child/attribute collections reflect later mutations.
- CharacterData `Data`, `Length`, substring/append/insert/delete/replace;
  Text `SplitText`/`WholeText`. Offsets and lengths use UTF-16 units. A boundary
  splitting a surrogate pair is explicitly rejected rather than repaired.
- Explicit `SetNamespaceMapping(prefix, uri[, False])`, removal and namespace
  lookup. URI-only automatic-prefix generation and reconcile=True are rejected,
  not silently interpreted as default-namespace mapping.
- `DOMBuilder.Read(XMLReader)` starts at the beginning of an open XML source;
  it follows that reader's settings and does not close it. `DOMWriter.Write(node,
  XMLWriter)` preserves node namespaces, including insertion inside an already
  opened target default namespace, and does not close the target.

English and Russian spellings follow the official EDT SyntaxHelper pages for
`catalog63/catalog1055`. These APIs are documented since 8.1, available on server,
thick client and external connection. The fixed measurement targets existing
8.3.27.1508 managed-thick-file/server contexts, not thin/web clients.
The reviewed primary archive SHA256 is
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.

## Integrity and finite scope

Each document has a cumulative allocation ledger: 10,000 nodes and 4,194,304
Unicode **code points**, including detached nodes, imported copies and replacement
text. This is a conservative lifetime resource admission limit, not a native DOM
limit or a UTF-16 byte count. Individual XML strings and serialized output retain
the existing writer's stricter 1,000,000-character bound. Depth is at most128;
walks are iterative and at most200,000 steps. Clones/imports preflight the complete
copy before allocating nodes. Graph mutation checks identity, ownership, cycles,
depth and document-root hierarchy before detaching or replacing anything.

DTD, entity declarations/resolution and external resources remain forbidden by
the existing bounded XML parser. No URL/network loader, new filesystem authority,
permission changes or callbacks are added. File paths are handled only by the
already opened XML reader/writer. Failed DOM reads restore the reader cursor;
failed serialization leaves the target's bounded in-memory state unchanged.
Borrowed file descriptors are neither copied nor closed by DOMWriter.

`!todo`: XPath, XSD, HTML, XDTO, DTD/default/ID attributes and entity nodes,
DOMConfiguration, ReadWithContext, positioned-subtree reads, traversal filters,
user data, document-position ordering, automatic prefix spelling/reconciliation,
attribute child-node/entity trees, XML1.1, unpaired-surrogate operations, exotic
XML name ranges, codecs and cross-context persistence are outside this block.
Unsupported overloads/features must fail explicitly; local negative guard tests
do not assert native exception equivalence. General storage and type-coercion
support is not implied by a node's `TypeOf` identity.

The source-bound40-case ordinary packet and exact admission/output limits are
specified in [dom-family-measurement.md](dom-family-measurement.md). Native facts
will calibrate defaults, return values, live lists, namespace behavior and reader
settings before parity is claimed. No public fixture may contain raw exceptions,
installation identifiers, credentials or uncontrolled filesystem paths.
