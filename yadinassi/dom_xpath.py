"""Measured default DOM XPath iterator and namespace resolver, in process only."""
from .dom_nodes import BSLDOMDocument, _node, K
from .file_io import _FileMethods, _methods
from .xml_writer import _name, _text, _XML_URI
from .dom_xpath_engine import evaluate


class BSLDOMNamespaceResolver(_FileMethods):
    _methods = {}
    def __init__(self, *args):
        if len(args) == 1:
            node = _node(args[0])
            if node._kind is K.DOCUMENT: node = node.document_element()
            if node is None: raise ValueError('XPath: resolver requires a document element')
            scope = dict(node._scope())
            if '' in scope: scope['xmlns'] = scope.pop('')
        elif len(args) == 2:
            prefix, uri = _text(args[0]), _text(args[1])
            _name(prefix, False)
            if not uri or prefix == 'xml' and uri != _XML_URI: raise ValueError('XPath: invalid namespace binding')
            scope = {prefix: uri}
        else: raise TypeError('XPath: resolver requires a node or prefix and URI')
        scope['xml'] = _XML_URI
        self._bindings = scope
    def __str__(self): return 'Разыменователь пространств имен DOM XPath'


class BSLDOMXPathResult(_FileMethods):
    _methods = _methods(('iterate_next', True, 'IterateNext Следующий'))
    def __init__(self, nodes): self._nodes = tuple(nodes); self._index = 0
    def __str__(self): return 'Результат DOM XPath'
    def get_member(self, name):
        if name.casefold() in ('invaliditeratorstate', 'неверноесостояниеитератора'): return False
        return super().get_member(name)
    def iterate_next(self):
        if self._index == len(self._nodes): return None
        result = self._nodes[self._index]; self._index += 1; return result


def evaluate_xpath(document, expression, context, resolver):
    if type(document) is not BSLDOMDocument or _node(context)._doc() is not document:
        raise ValueError('XPath: context belongs to another document')
    if type(resolver) is not BSLDOMNamespaceResolver: raise TypeError('XPath: namespace resolver required')
    return BSLDOMXPathResult(evaluate(document, expression, context, resolver._bindings))
