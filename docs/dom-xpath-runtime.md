# Bounded DOM XPath paths

`DOMNamespaceResolver(Node)` and `DOMNamespaceResolver(Prefix, URI)` supply a
closed namespace snapshot. `DOMDocument.EvaluateXPathExpression(Expression,
ContextNode, Resolver)` returns a `DOMXPathResult` with `IterateNext()` and the
readonly `InvalidIteratorState` flag. Context must belong to that document.
This checkpoint exposes the measured English API spellings; additional aliases
are not inferred from prose translations.

Supported paths: absolute/relative child paths, `//`, `.`, `..`, element names,
`*`, namespace-prefixed names/wildcards, `@` attributes, `node()`, `text()`,
`comment()` and `processing-instruction()`. Predicates are positive integer
positions, `last()`, attribute existence and attribute-string equality. Position
predicates apply per parent; this matters for `//item[1]`. Namespace declarations
are not ordinary attribute-axis results. A node-derived resolver maps the default
namespace to the measured `xmlns` prefix; unprefixed names select no namespace.
Unknown prefixes refuse even when an earlier step would yield no nodes.

The default iterator retains selected node identities. Native run 43093418847
observed `InvalidIteratorState=False` after insertion, attribute/text changes,
and namespace-mapping changes. The implementation does not invent revision
invalidation from W3C expectations. Retained mutable nodes remain the same nodes.
This does not establish arbitrary mutation/iterator parity beyond those cases.

Expression length, steps, predicates, result size, depth and cumulative traversal
work are bounded locally. Variables, arbitrary axes, scalar expressions, unions,
extension functions, external resources, XPath result-type selection, general
XPath/XSD compatibility, serialization and cross-context transport are not added.

The immutable native fixture was recovered from the original GitHub artifacts:
run 43093418847, merge 202fb7f7a17fd49691be1a8e5eb213c63fcd7fa0,
tree 33215b3130b651128cb00e153838fa80eebdfe5c. Source hashes, merge parents,
nonce/module/output agreement and cleanup were reverified. Recovered runtime
bytes require new local and CI validation; earlier runtime test results are not
used to certify this reconstruction.
