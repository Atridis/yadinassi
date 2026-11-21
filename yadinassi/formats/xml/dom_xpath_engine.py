"""Closed XPath location-path evaluator over the existing owned DOM graph.

Not a general XPath library: no extension functions, scalar evaluation, external
resources, variables or expression language. Every traversal shares one budget.
"""
import re
from .dom_nodes import K, MAX_NODES, MAX_DEPTH, MAX_WORK
from .xml_writer import _name, _XMLNS_URI

MAX_EXPRESSION = 4096
MAX_STEPS = 128
MAX_PREDICATES = 16


def _qname(text):
    if text == '*': return text
    if text.endswith(':*'):
        _name(text[:-2], False)
        return text
    _name(text)
    if text.count(':') > 1: raise ValueError('XPath: invalid qualified name')
    return text


def _step(text):
    base = text.split('[', 1)[0].strip()
    if base in ('.', '..'): axis, name = ('self', 'node()') if base == '.' else ('parent', 'node()')
    elif base.startswith('@'): axis, name = 'attribute', _qname(base[1:])
    else:
        axis, name = 'child', base
        if name not in ('node()', 'text()', 'comment()', 'processing-instruction()'): _qname(name)
    rest = text[len(text.split('[', 1)[0]):]; predicates = []
    while rest:
        if not rest.startswith('['): raise ValueError('XPath: unsupported predicate')
        quote = None; end = None
        for i, c in enumerate(rest[1:], 1):
            if quote:
                if c == quote: quote = None
            elif c in ('"', "'"): quote = c
            elif c == ']': end = i; break
            elif c == '[': raise ValueError('XPath: nested predicates unsupported')
        if end is None: raise ValueError('XPath: unterminated predicate')
        p = rest[1:end].strip(); rest = rest[end+1:].strip()
        if re.fullmatch(r'[0-9]{1,8}', p): predicates.append(('position', int(p)))
        elif p == 'last()': predicates.append(('last', None))
        else:
            m = re.fullmatch(r'@([^\s=]+)\s*(?:=\s*([\'"])(.*?)\2)?', p, re.S)
            if not m: raise ValueError('XPath: unsupported predicate')
            predicates.append(('attribute', _qname(m[1]), m[3]))
        if len(predicates) > MAX_PREDICATES: raise ValueError('XPath: predicate limit')
    return axis, name, tuple(predicates)


def parse(expression):
    if type(expression) is not str or not expression or len(expression) > MAX_EXPRESSION:
        raise ValueError('XPath: invalid expression length')
    expression = expression.strip()
    if expression == '/': return True, ()
    absolute = expression.startswith('/')
    i = 0; descendant = False
    if absolute:
        i = 1
        if expression.startswith('//'): i = 2; descendant = True
    steps = []; start = i; bracket = 0; quote = None
    while i <= len(expression):
        c = expression[i] if i < len(expression) else '/'
        if quote:
            if c == quote: quote = None
        elif c in ('"', "'"): quote = c
        elif c == '[': bracket += 1
        elif c == ']':
            bracket -= 1
            if bracket < 0: raise ValueError('XPath: unmatched predicate')
        elif c == '/' and bracket == 0:
            part = expression[start:i].strip()
            if not part: raise ValueError('XPath: empty step')
            steps.append((descendant, _step(part)))
            if len(steps) > MAX_STEPS: raise ValueError('XPath: step limit')
            if i == len(expression): break
            descendant = i + 1 < len(expression) and expression[i+1] == '/'
            i += 1 if descendant else 0
            start = i + 1
        i += 1
    if quote or bracket: raise ValueError('XPath: unterminated expression')
    return absolute, tuple(steps)


class Budget:
    def __init__(self): self.work = 0
    def charge(self, n=1):
        self.work += n
        if self.work > MAX_WORK: raise ValueError('XPath: work limit')


def _descendants(node, budget):
    pending = [(node, 0)]
    while pending:
        node, depth = pending.pop(); budget.charge()
        if depth > MAX_DEPTH: raise ValueError('XPath: depth limit')
        yield node
        pending.extend((x, depth + 1) for x in reversed(node._children))


def _expanded(name, resolver):
    if name in ('*', 'node()', 'text()', 'comment()', 'processing-instruction()'): return name
    if ':' not in name: return ('', name)
    prefix, local = name.split(':')
    if prefix not in resolver: raise ValueError('XPath: unresolved namespace prefix')
    return (resolver[prefix], local)


def _matches(node, name, axis):
    if name == 'node()': return True
    if name == 'text()': return node._kind in (K.TEXT, K.CDATA)
    if name == 'comment()': return node._kind is K.COMMENT
    if name == 'processing-instruction()': return node._kind is K.PI
    if node._kind is not (K.ATTRIBUTE if axis == 'attribute' else K.ELEMENT): return False
    if node._uri == _XMLNS_URI: return False
    if name == '*': return True
    uri, local = name
    return node._uri == uri and (local == '*' or (node._local or node._name) == local)


def evaluate(document, expression, context, namespaces):
    absolute, steps = parse(expression); budget = Budget()
    # Resolve every prefix before walking, including a path whose first step is empty.
    compiled = []
    for descendants, (axis, name, predicates) in steps:
        predicates = tuple((p[0], _expanded(p[1], namespaces), p[2]) if p[0] == 'attribute' else p for p in predicates)
        compiled.append((descendants, axis, _expanded(name, namespaces), predicates))
    current = [document if absolute else context]
    for descendants, axis, name, predicates in compiled:
        output = []; seen = set()
        for root in current:
            parents = _descendants(root, budget) if descendants else (root,)
            for parent in parents:
                budget.charge()
                if axis == 'self': candidates = (parent,)
                elif axis == 'parent':
                    owner = parent._owner_element if parent._kind is K.ATTRIBUTE else parent._parent
                    candidates = () if owner is None else (owner,)
                else: candidates = parent._attrs if axis == 'attribute' else parent._children
                matched = []
                for node in candidates:
                    budget.charge()
                    if _matches(node, name, axis): matched.append(node)
                for p in predicates:
                    if p[0] == 'position': matched = matched[p[1]-1:p[1]] if p[1] else []
                    elif p[0] == 'last': matched = matched[-1:]
                    else:
                        filtered = []
                        for node in matched:
                            budget.charge()
                            for attr in node._attrs:
                                budget.charge()
                                if _matches(attr, p[1], 'attribute') and (p[2] is None or attr._data == p[2]):
                                    filtered.append(node); break
                        matched = filtered
                for node in matched:
                    budget.charge()
                    if id(node) not in seen:
                        seen.add(id(node)); output.append(node)
                        if len(output) > MAX_NODES: raise ValueError('XPath: result limit')
        current = output
    return tuple(current)
