"""Per-node facts for fresh local Structures and pure scalar expressions.

Opaque operations invalidate knowledge, not execution: later fresh assignments
can establish new facts. No runtime admission, cached owner, or value traversal.
"""
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from yadinassi.syntax import ast as bsl
from yadinassi.execution.codegen.experimental_naked_structure import prepare_structure_schema


@dataclass
class _Structure:
    fields: dict


class _Opaque(Exception):
    pass


def analyze(program, opaque_names=(), *, routines=None):
    fields = {}
    scalars = {}
    opaque = set(opaque_names) | {'thisobject', 'этотобъект'}
    routines = routines or {}
    pure_returns = {}
    call_results = {}

    def require(ok):
        if not ok:
            raise _Opaque

    def pure_return(name):
        if name not in pure_returns:
            routine = routines.get(name)
            result = None
            if (routine is not None and routine.is_function and len(routine.body) == 1
                    and type(routine.body[0]) is bsl.Return and all(p.by_value for p in routine.parameters)):
                params = tuple(p.name.casefold() for p in routine.parameters)
                value = routine.body[0].value
                pending = [value]
                while pending:
                    node = pending.pop()
                    kind = type(node)
                    if kind is bsl.Group:
                        pending.append(node.expression)
                    elif kind is bsl.Unary:
                        pending.append(node.operand)
                    elif kind is bsl.Binary:
                        pending.extend((node.left, node.right))
                    elif kind is not bsl.Literal and not (kind is bsl.Name and node.name.casefold() in params):
                        break
                else:
                    result = params, value
            pure_returns[name] = result
        return pure_returns[name]

    def expression(node, env):
        kind = type(node)
        if kind is bsl.Literal:
            value = node.value
            result = {Decimal:'number', int:'number', str:'string', bool:'bool', type(None):'none'}.get(type(value))
            require(result is not None)
        elif kind is bsl.Name:
            key = node.name.casefold()
            require(key not in opaque and key in env)
            result = env[key]
        elif kind is bsl.Group:
            result = expression(node.expression, env)
        elif kind is bsl.New:
            require(node.name.casefold() in ('structure','структура'))
            args = node.arguments
            require(not args or type(args[0]) is bsl.Literal and type(args[0].value) is str)
            try:
                schema = prepare_structure_schema(args[0].value if args else '')
            except ValueError:
                raise _Opaque from None
            values = [expression(arg, env) for arg in args[1:]]
            result = _Structure({key:values[index] if index < len(values) else 'none'
                                 for key, spelling, index in schema})
        elif kind is bsl.Attribute:
            owner = expression(node.object, env)
            require(type(owner) is _Structure and node.name.casefold() in owner.fields)
            fields[id(node)] = 'structure'
            result = owner.fields[node.name.casefold()]
        elif kind is bsl.Call and type(node.callee) is bsl.Name:
            name = node.callee.name.casefold()
            signature = pure_return(name)
            require(signature is not None)
            params, returned = signature
            require(len(node.arguments) == len(params))
            arguments = tuple(expression(arg, env) for arg in node.arguments)
            require(all(type(arg) is str for arg in arguments))
            key = name, arguments
            if key not in call_results:
                before = len(scalars)
                try:
                    call_results[key] = expression(returned, dict(zip(params, arguments)))
                finally:
                    while len(scalars) > before:
                        scalars.popitem()
            result = call_results[key]
        elif kind is bsl.Unary:
            operand = expression(node.operand, env)
            require(operand in ('number','bool'))
            if node.operator == 'NOT':
                result = 'bool'
            else:
                require(node.operator in ('+','-') and operand == 'number')
                result = 'number'
        elif kind is bsl.Binary:
            left = expression(node.left, env)
            right = expression(node.right, env)
            op = node.operator
            if op in ('+','-','*','/','%'):
                require(left == right == 'number' or op == '+' and left == 'string' and right in ('string','number','bool','none'))
                result = left
            elif op in ('=','<>','<','<=','>','>='):
                require(left == right and left in ('number','string','bool'))
                result = 'bool'
            else:
                require(op in ('AND','OR') and left in ('number','bool') and right in ('number','bool'))
                result = 'bool'
        else:
            raise _Opaque
        if type(result) is _Structure:
            scalars[id(node)] = 'structure'
        elif type(result) is str and result in ('number','string','bool'):
            scalars[id(node)] = result
        return result

    def shape(env):
        identities = {}
        def describe(value):
            if type(value) is not _Structure:
                return value
            identity = id(value)
            if identity in identities:
                return ('ref', identities[identity])
            index = len(identities)
            identities[identity] = index
            return ('structure', index, tuple((key, describe(child))
                    for key,child in sorted(value.fields.items())))
        return tuple((key, describe(value)) for key,value in sorted(env.items()))

    def statement(node, env):
        kind = type(node)
        if kind is bsl.Assign:
            if type(node.target) is bsl.Name:
                key = node.target.name.casefold()
                require(key not in opaque)
                env[key] = expression(node.value, env)
            elif type(node.target) is bsl.Attribute:
                owner = expression(node.target.object, env)
                key = node.target.name.casefold()
                require(type(owner) is _Structure and key in owner.fields)
                value = expression(node.value, env)
                owner.fields[key] = value
                fields[id(node)] = 'structure'
            else:
                raise _Opaque
        elif kind is bsl.ExpressionStatement:
            expression(node.expression, env)
        elif kind is bsl.For:
            require(expression(node.start, env) == expression(node.end, env) == 'number')
            key = node.name.casefold()
            require(key not in opaque)
            env[key] = 'number'
            before = deepcopy(env)
            nested = deepcopy(env)
            for item in node.body:
                statement(item, nested)
            # Earlier reads must remain valid on every subsequent iteration.
            require(all(name in nested for name in before))
            require(shape(before) == shape({name:nested[name] for name in before}))
            # A zero-trip loop must not manufacture initialized names.
            env.clear(); env.update(before)
        else:
            raise _Opaque

    env = {}
    for node in program:
        if type(node) is bsl.Routine:
            continue
        saved_fields = len(fields)
        saved_scalars = len(scalars)
        try:
            statement(node, env)
        except (_Opaque, RecursionError):
            while len(fields) > saved_fields:
                fields.popitem()
            while len(scalars) > saved_scalars:
                scalars.popitem()
            env.clear()
    return fields, scalars
