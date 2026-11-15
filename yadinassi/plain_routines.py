"""Narrow whole-routine research lowering, after live runtime admission.

Only immutable owned synchronous Val Decimal routines; opaque or policy-owned
execution remains on the existing compiled adapter. Not a Python sandbox.
"""
from dataclasses import dataclass
from decimal import Decimal
from .syntax import ast
from .owned_syntax import syntax_kind
from .compiled_inline import _CODE_CACHE

class Ineligible(Exception): pass

@dataclass(frozen=True)
class PlainRoutine:
    function: object
    parameters: tuple
    names: frozenset
    source: str


def lower(routine, *, max_source_bytes=100000):
    if (syntax_kind(routine) is not ast.Routine or not routine.is_function
            or routine.is_async or routine.is_dual
            or any(not p.by_value or p.default is not None for p in routine.parameters)):
        raise Ineligible()
    parameters=tuple(p.name.casefold() for p in routine.parameters)
    if len(set(parameters))!=len(parameters):raise Ineligible()
    slots={name:'v'+str(i) for i,name in enumerate(parameters)}
    known=set(parameters);constants=[];nodes=[];lines=[];serial=0
    def emit(depth,text):lines.append('    '*depth+text)
    def temp():
        nonlocal serial
        serial+=1;return 't'+str(serial)
    def slot(name):
        name=name.casefold()
        if name not in slots:slots[name]='v'+str(len(slots))
        return slots[name]
    def boundary(node,depth,produce):
        if depth>12 or len(nodes)>2048:raise Ineligible()
        index=len(nodes);nodes.append(node)
        emit(depth,'try:');result=produce(depth+1)
        emit(depth,'except BaseException as error:')
        emit(depth+1,f'converted = vm.compiled_exception(nodes[{index}], error)')
        emit(depth+1,'if converted is error: raise')
        emit(depth+1,'raise converted from None')
        return result
    def expr(node,depth):
        kind=syntax_kind(node)
        def produce(d):
            value=temp()
            if kind is ast.Name:
                if node.name.casefold() not in known:raise Ineligible()
                emit(d,f'{value} = {slot(node.name)}')
            elif kind is ast.Literal and type(node.value) is Decimal:
                constants.append(node.value);emit(d,f'{value} = constants[{len(constants)-1}]')
            elif kind is ast.Binary and node.operator in ('+','-','*'):
                left=expr(node.left,d);right=expr(node.right,d)
                emit(d,f'{value} = {left} {node.operator} {right}')
            else:raise Ineligible()
            return value
        return boundary(node,depth,produce)
    def statement(node,depth):
        kind=syntax_kind(node)
        def produce(d):
            if kind is ast.Assign and syntax_kind(node.target) is ast.Name:
                value=expr(node.value,d);name=node.target.name.casefold()
                emit(d,f'{slot(name)} = {value}');known.add(name)
            elif kind is ast.Return:
                value=expr(node.value,d);emit(d,f'return {value}')
            elif kind is ast.For:
                first=expr(node.start,d);last=expr(node.end,d);counter=slot(node.name)
                emit(d,f'{counter} = {first}');known.add(node.name.casefold());before=set(known)
                emit(d,f'while {counter} <= {last}:')
                for child in node.body:statement(child,d+1)
                emit(d+1,f'{counter} = {counter} + ONE')
                known.intersection_update(before)
            else:raise Ineligible()
        boundary(node,depth,produce)
    if not routine.body or syntax_kind(routine.body[-1]) is not ast.Return:raise Ineligible()
    lines.append('def lowered(vm, '+', '.join(slots.values())+'):')
    for node in routine.body:statement(node,1)
    source='\n'.join(lines)+'\n'
    if len(source.encode())>min(100000,max_source_bytes):raise Ineligible()
    namespace={'nodes':tuple(nodes),'constants':tuple(constants),'ONE':Decimal(1)}
    exec(_CODE_CACHE.get(source),namespace)
    return PlainRoutine(namespace['lowered'],parameters,frozenset(slots),source)
