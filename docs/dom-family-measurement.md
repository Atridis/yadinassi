# Ordinary DOM workflow measurement

One closed packet (`dom-family-v1`, case `dom_family`) covers 40 ordinary
workflows. The first completed native capture is retained below; five ordinary
semantic discriminants are captured and locally replayed; fresh-head parity is pending. Local observations and synthetic wire
fixtures are not platform evidence or expected native semantic values.

## Primary source and boundaries

The official EDT archive SHA256 is
`a8cf9c3cd5d7828958dcf69d8864cf6664180260e4d50cbff338921304c7e642`.
The inspected pages are `nl/ru/html/SyntaxHelperContext/objects/catalog63/catalog1055/`
for DOMBuilder, DOMWriter, DOMDocument, DOMElement, DOMAttribute, DOMText,
DOMCDATASection, DOMComment, DOMProcessingInstruction, DOMDocumentFragment,
DOMNodeList, DOMElementList and DOMAttributeMap. They document server/thick-client
availability; no thin/web availability is inferred. Target native context and
version must be recorded in the acquisition evidence.

The APIs are the documented 1C spellings: `GetElementByTagName` (singular),
collection `Count()`/`Item(index)`, namespace overloads rather than invented `NS`
methods. Document construction supplies both URI and qualified root name.
Clone/import supply their required deep flag explicitly. Builder and writer use
ordinary defaults, without changing configuration/security settings.

## Case map

| Cases | Ordinary coverage |
| --- | --- |
| 1–8 | Root/owner/default properties; append, insert, replace, remove, live child list, existing-child move; mutation return identities |
| 9–13 | Unicode including astral text, text replacement, character-data editing, split/whole text, normalization |
| 14–17 | CDATA, comment, processing instruction, fragment transfer |
| 18–24 | Attributes, replacement/removal, specified/ID flags, owner, live map and named/indexed access |
| 25–30 | Qualified element/attribute, namespace lookup, document/element tag search, list liveness and namespace-filter discriminants |
| 31–34 | Shallow/deep clone and import, identity/equality/ownership distinctions |
| 35–39 | XMLReader/DOMBuilder string parsing; CDATA/comment/PI defaults; DOMWriter/XMLWriter escaping, namespaces and element-only roundtrip |
| 40 | Owned XML file write/read/close/delete workflow |

Raw serialization and generated paths are not compared: roundtrips inspect
semantic content. This avoids imposing platform-specific whitespace, declaration,
namespace-prefix or temporary-path representations. Semantic differences remain
observations for subsequent calibration; the wire validator does not turn them
into boolean expected answers. No intentional invalid native workflow is invoked.

## Closed wire and cleanup

Source SHA256:
`0b4defe51038890513cc778e8616153649faf676423c92fdb637d34de7b96db3`.
Source is 8185 UTF-8 bytes under the unchanged 8192-byte source bound.
Two calibration lines exercise empty and six-UTF16-unit text including NBSP,
semicolon, quote and an astral surrogate pair. Forty ordered `DM-01`–`DM-40`
records encode at most 40 UTF-16 units each as four lowercase hexadecimal digits.
Maximum complete output is 7130 bytes under the unchanged 8192-byte output bound.
Action failure and observer failure are distinct fixed tokens; neither exports
exception text, credentials, paths or arbitrary diagnostic input. Acceptance
requires all 40 actions and the observer controls, not merely valid framing.

The single file scenario refuses a pre-existing generated fixture root, creates
only `a.xml`, closes both XML resources on failure, removes only that exact known
file, and removes the directory only when empty. Unexpected children are not
recursively swept. Tests inject a writer failure, an unexpected sentinel and a
fixture-root collision solely within test-owned temporary directories.

`!todo`: DTD/entities, XPath, HTML, schema validation, exotic configuration,
external resources and advanced traversal are outside this ordinary batch. No
external entities, network, permissions, environment overrides or new CI triggers
are introduced. Shared profile/workflow wiring is coordinated by the owner.


## Local integration checkpoint

The closed profile, host/producer dispatch, shell stage flag and one existing
native workflow matrix row are now integrated. No new trigger, secret, permission
or resource cap was introduced. Local40 availability is not native parity.

## Initial acquisition boundary

The original source (SHA256 `8d4afe77fc2691bcd4673bd2f80f1e7f1576935a4685feff23d5b94ac97c5afb`) reached a client ENTERPRISE timeout after the server case completed its validation. No raw forty-case capture was exported; this is not native parity evidence. Its English helper declaration keywords did not match the existing Russian-keyword client-context injector. The revised packet uses the same declaration spelling as the previously validated profiles; a generated-module regression requires all six helpers to receive explicit client context. Runtime, observations, process limits and acceptance rules are unchanged. The timeout's exact internal platform cause remains unavailable without new evidence.

## First completed native capture and bounded discriminants

The corrected client-context packet completed server and managed-thick-file execution with identical forty records and verified cleanup. Minimal immutable source/output/receipt are retained in `tests/fixtures/dom_family/native-initial-v1`; private installation/session/provenance metadata are not included. Its 37 `ok` and three `action-error` records are not full parity: cases 12, 29, 30, 31 and 36 differ from the provisional runtime. The private audit validated 53 source/provenance conditions using a reconstructed transport envelope, not a retained original envelope.

The current packet retains 40 IDs and bounded output, with phase-isolated ordinary observations in those five slots: SplitText versus WholeText; query counts before/after mutation versus item access; one/two-argument query discrimination; cloning versus reading the returned node; and parsed node kinds. Short pure conversion/element-construction helpers make room without raising the source bound. All helpers require explicit generated client context. No runtime semantics, global XMLReader settings, native timeout or acceptance criteria were changed speculatively. The original thirty-five matching observations remain covered by immutable replay.

## Measured ordinary calibration

The current discriminant capture has 40 available values in both contexts. SplitText mutates the adjacent text tree and returns Undefined. Document tag queries are snapshots and the measured name/URI overload selects local-name matches across the tested prefixed/empty namespaces. Element queries are not generalized from Document observations. Shallow element clone omits attributes; deep clone and ImportNode retain their prior behavior. DOMBuilder retains comments without changing ordinary XMLReader defaults or the borrowed reader settings; CDATA still follows the measured default text handling. All mutations retain their existing bounded preflight.

The original capture remains byte-identical. Its shallow-clone aggregate action-error is retained and reproduced: missing attributes return Undefined (official GetAttribute contract), so the original expression beginning with that value fails rather than assuming an empty string. No blanket exception parity or unmeasured namespace-pattern behavior is claimed. The current complete fixed40 replay is retained separately, and fresh native execution on the corrected runtime is required before parity acceptance.
