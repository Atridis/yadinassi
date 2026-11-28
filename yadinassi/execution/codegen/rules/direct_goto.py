"""Lexical jump planning for the shared Python emitter."""
from yadinassi.syntax import ast as bsl
from yadinassi.syntax.parser import validate_labels


class GotoTransfer(BaseException):
    """Escape an inner Python block without being caught by BSL Except."""
    __slots__ = ('target',)

    def __init__(self, target):
        self.target = target


def nested_blocks(node):
    kind = type(node)
    if kind is bsl.If:
        return (*(body for _, body in node.branches), node.otherwise)
    if kind is bsl.Try:
        return node.body, node.handler
    if kind in (bsl.For, bsl.ForEach, bsl.While, bsl.Routine, bsl.ServerInitializer):
        return (node.body,)
    return ()


def has_goto(program):
    pending = [program]
    while pending:
        for node in pending.pop():
            if type(node) is bsl.Goto:
                return True
            pending.extend(nested_blocks(node))
    return False


def plan(program, unsupported):
    validate_labels(program)
    destinations, transfers = {}, {}
    seen = set()
    roots = [(program, None)]
    while roots:
        root, routine = roots.pop()
        labels, jumps = {}, []
        pending = [root]
        while pending:
            body = pending.pop()
            for node in body:
                kind = type(node)
                if kind in (bsl.Goto, bsl.Label):
                    if id(node) in seen:
                        raise unsupported('Goto and Label require distinct AST nodes')
                    seen.add(id(node))
                if kind is bsl.Label:
                    labels[node.name.casefold()] = node, body
                elif kind is bsl.Goto:
                    jumps.append((node, body))
                elif kind in (bsl.Routine, bsl.ServerInitializer):
                    roots.append((node.body, node))
                else:
                    pending.extend(nested_blocks(node))
        outward = {id(labels[jump.name.casefold()][1]) for jump, body in jumps
                   if body is not labels[jump.name.casefold()][1]}
        if outward and routine is not None and any(type(node) is bsl.Var for node in root):
            raise unsupported('Goto with variable declarations in an outward target is unsupported')
        for label, body in labels.values():
            if id(body) in outward:
                destinations[id(label)] = len(destinations)
        for jump, _ in jumps:
            label, _ = labels[jump.name.casefold()]
            if id(label) in destinations:
                transfers[id(jump)] = destinations[id(label)]
    return destinations, transfers


def linear_path(nodes):
    """Follow static local jumps; a list has at most one reachable cycle."""
    labels = {node.name.casefold(): i for i, node in enumerate(nodes) if type(node) is bsl.Label}
    order, visited = [], {}
    i = 0
    while i < len(nodes) and i not in visited:
        visited[i] = len(order)
        node = nodes[i]
        if type(node) is bsl.Goto and node.name.casefold() in labels:
            i = labels[node.name.casefold()]
        else:
            if type(node) is not bsl.Label:
                order.append(node)
            if type(node) is bsl.Goto:  # The enclosing dispatcher receives it.
                return order, None
            i += 1
    if i not in visited:
        return order, None
    start = visited[i]
    return order[:start], order[start:]


def check_cycle(nodes, routine_names, unsupported):
    pending = list(nodes)
    while pending:
        node = pending.pop()
        kind = type(node)
        if kind in (bsl.Break, bsl.Continue, bsl.Var):
            raise unsupported('Goto cycle with outer loop control or variable declarations is unsupported')
        if kind is bsl.Assign and type(node.target) is bsl.Name and node.target.name.casefold() in routine_names:
            raise unsupported('Goto cycle with routine shadow is unsupported')
        if kind in (bsl.If, bsl.Try):
            for body in nested_blocks(node):
                pending.extend(body)
