"""Trusted, side-separated managed form programs; never a wire code format."""
from copy import deepcopy
from dataclasses import dataclass, fields
from hashlib import sha256

from .syntax import ast
from .syntax.parser import parse
from .form_model import text
from .invocation import InvocationBinding, MAX_ENDPOINTS

_SEAL = object()


class FormSideProgram:
    """Compiler-owned AST snapshot. Every interpreter receives its own copy."""
    __slots__ = ('side', 'source_sha256', '__nodes')

    def __init__(self, side, nodes, digest, *, _seal=None):
        if _seal is not _SEAL:
            raise TypeError('compile_form_module must create form programs')
        self.side = side
        self.source_sha256 = digest
        self.__nodes = deepcopy(nodes)

    def program(self):
        return deepcopy(self.__nodes)


def admitted_program(source, *, side=None, label='<form-module>', compilation_profile=None):
    if type(source) is FormSideProgram:
        if side is not None and source.side != side:
            raise ValueError('wrong form program side')
        return source.program()
    text(source, 65536)
    if compilation_profile is None:
        return parse(source, label)
    return parse(source, label, compilation_profile=compilation_profile)


@dataclass(frozen=True)
class FormProgram:
    client: FormSideProgram
    server: FormSideProgram
    nocontext: FormSideProgram
    handlers: tuple
    server_bindings: tuple
    nocontext_bindings: tuple
    source_sha256: str

    @property
    def endpoints(self):
        return {b.endpoint: b.name for b in self.server_bindings}

    @property
    def nocontext_endpoints(self):
        return {b.endpoint: b.name for b in self.nocontext_bindings}



def _object_projection(node, mapping, *, context='server'):
    """Lower checked Object.member paths to private scalar form attributes.

    This is compiler admission, not source substitution or a second evaluator.
    No object receiver/identity is retained in the program or wire packet.
    """
    roots = {'object', 'объект'}
    if (isinstance(node, ast.Call) and isinstance(node.callee, ast.Name)
            and node.callee.name.casefold() == 'writeobject'
            and (context != 'server' or node.arguments)):
        raise ValueError('WriteObject requires a context server and no arguments')
    if isinstance(node, (ast.Attribute, ast.Index)) and isinstance(node.object, ast.Attribute):
        base = node.object.object
        if isinstance(base, ast.Name) and base.name.casefold() in roots:
            raise ValueError('nested object form expressions unsupported')
    if isinstance(node, ast.Attribute) and isinstance(node.object, ast.Name) and node.object.name.casefold() in roots:
        target = mapping.get(node.name.casefold())
        if context == 'nocontext' or target is None:
            raise ValueError('unsupported object form member or NoContext access')
        return ast.Name(node.token, target)
    if isinstance(node, ast.Name):
        if node.name.casefold() in roots or node.name.casefold().startswith('objectfield'):
            raise ValueError('object form receiver cannot escape or be shadowed')
    if isinstance(node, (ast.Routine, ast.Parameter, ast.For, ast.ForEach)):
        if node.name.casefold() in roots or node.name.casefold().startswith('objectfield'):
            raise ValueError('reserved object form declaration')
    if isinstance(node, ast.Var):
        if any(n.casefold() in roots or n.casefold().startswith('objectfield') for n in node.names):
            raise ValueError('reserved object form variable')
    if isinstance(node, list):
        return [_object_projection(value, mapping, context=context) for value in node]
    if isinstance(node, tuple):
        return tuple(_object_projection(value, mapping, context=context) for value in node)
    if isinstance(node, ast.Node):
        for field in fields(node):
            if field.name == 'token':
                continue
            value = getattr(node, field.name)
            if isinstance(value, ast.Node):
                setattr(node, field.name, _object_projection(value, mapping, context=context))
            elif isinstance(value, (list, tuple)):
                setattr(node, field.name, _object_projection(value, mapping, context=context))
    return node


def compile_form_module(source, *, object_fields=()):
    text(source, 65536)
    if type(object_fields) is not tuple or len(object_fields) > 128:
        raise ValueError('bounded object field inventory required')
    projection = {}
    for index, member in enumerate(object_fields, 1):
        if (type(member) is not str or not member.isidentifier() or len(member) > 128
                or member.casefold() in projection):
            raise ValueError('invalid object field inventory')
        projection[member.casefold()] = 'ObjectField' + str(index)
    nodes = parse(source, '<configuration-form>')
    if len(nodes) > 256:
        raise ValueError('form declaration limit')
    sides = {'client': [], 'server': [], 'nocontext': []}
    handlers, endpoints, calls = [], [], []
    names = set()
    for node in nodes:
        if not isinstance(node, (ast.Var, ast.Routine)):
            raise ValueError('form module permits declarations only')
        declared = [node.name] if isinstance(node, ast.Routine) else node.names
        for name in declared:
            key = name.casefold()
            if key in names or key in ('openform', 'открытьформу', 'parameters', 'параметры'):
                raise ValueError('duplicate or reserved form declaration')
            names.add(key)
        side = node.execution_context
        if isinstance(node, ast.Routine):
            if node.is_async or node.is_dual:
                raise ValueError('asynchronous and dual form routines unsupported')
            if not node.module_context:
                side = 'nocontext'
            target = None
            if side == 'client' and not node.is_function:
                target = handlers
            elif side in ('server', 'nocontext') and all(p.by_value and p.default is None for p in node.parameters):
                target = calls if side == 'nocontext' else endpoints
            if target is not None:
                target.append(InvocationBinding(node.name, len(target) + 1,
                    tuple(p.name for p in node.parameters), node.is_function))
            if side == 'nocontext' and target is None:
                raise ValueError('NoContext routines require explicit Val arguments')
        if side not in sides:
            raise ValueError('unsupported form execution context')
        if projection:
            node = _object_projection(node, projection, context=side)
        sides[side].append(node)
        if side == 'nocontext':
            # Same-server calls use the ordinary interpreter NoContext route;
            # only client calls use InvocationPort. No server body enters client.
            sides['server'].append(node)
    if any(len(x) > MAX_ENDPOINTS for x in (handlers, endpoints, calls)):
        raise ValueError('form endpoint limit')
    digest = sha256(source.encode('utf-8')).hexdigest()
    return FormProgram(*(FormSideProgram(side, sides[side], digest, _seal=_SEAL)
        for side in ('client', 'server', 'nocontext')),
        tuple(handlers), tuple(endpoints), tuple(calls), digest)
