"""Internal module-block lowering prototype; not wired into production dispatch.

The caller MUST retain execute_program preflight, declaration publication/imports,
then admit the exact filtered owned block transactionally. Generated functions
require an already validated pure root execution context and canonical globals.
This module's storage check alone is NOT an authority/ABI/provenance gate.
"""
from dataclasses import dataclass
from decimal import Decimal
from .syntax import ast
from .owned_syntax import syntax_kind, is_owned
from .plain_routines import Ineligible
from .compiled_inline import _CODE_CACHE

_SCALARS = (Decimal, bool, str, type(None))
_RESERVED = frozenset(('thisobject', 'этотобъект'))

@dataclass(frozen=True)
class PlainModule:
    block: object
    function: object
    source: str
    required_inputs: frozenset
    names: frozenset
    writes: frozenset

    @property
    def source_bytes(self):
        return len(self.source.encode('utf-8'))

    def storage_eligible(self, storage, imports):
        """Conservative inert storage check, AFTER caller's execution gate."""
        if type(storage) is not dict or type(imports) is not dict:
            return False
        if any(type(k) is not str for k in storage) or any(type(k) is not str for k in imports):
            return False
        if self.names & imports.keys() or not self.required_inputs <= storage.keys():
            return False
        return all(any(type(storage[name]) is kind for kind in _SCALARS)
                   for name in self.names if name in storage)


def lower_module(block, *, max_source_bytes=100000):
    """Prepare all-or-nothing code, without reading VM state or executing BSL.

    Caller charges source_bytes against aggregate admission budget before use.
    Every store is write-through; errors preserve earlier globals/loop updates.
    Unsupported syntax rejects the entire optional plan, never executes a prefix.
    """
    if not is_owned(block):
        raise Ineligible('owned admitted module block required')
    lines=['def lowered(vm, storage):', '    result = None']
    nodes=[]; constants=[]; required=set(); names=set(); writes=set(); known=set()
    serial=0; loop_depth=0
    def emit(depth, text): lines.append('    '*depth+text)
    def temp():
        nonlocal serial
        serial+=1
        return 't'+str(serial)
    def name(value, *, write=False):
        if type(value) is not str:raise Ineligible('non-string name')
        value=value.casefold()
        if value in _RESERVED:raise Ineligible('receiver-owned name')
        names.add(value)
        if write:writes.add(value)
        elif value not in known:required.add(value)
        return value
    def boundary(node, depth, produce):
        if depth>16 or len(nodes)>=2048:raise Ineligible('size/depth budget')
        index=len(nodes);nodes.append(node)
        emit(depth,'try:')
        result=produce(depth+1)
        emit(depth,'except BaseException as error:')
        emit(depth+1,f'converted = vm.compiled_exception(nodes[{index}], error)')
        emit(depth+1,'if converted is error: raise')
        emit(depth+1,'raise converted from None')
        return result
    def expr(node, depth):
        kind=syntax_kind(node)
        def produce(d):
            value=temp()
            if kind is ast.Literal and any(type(node.value) is k for k in _SCALARS):
                constants.append(node.value);emit(d,f'{value} = constants[{len(constants)-1}]')
            elif kind is ast.Name:
                key=name(node.name);emit(d,f'{value} = storage[{key!r}]')
            elif kind is ast.Group:
                operand=expr(node.expression,d);emit(d,f'{value} = {operand}')
            elif kind is ast.Unary and node.operator in ('+','-','NOT'):
                operand=expr(node.operand,d);emit(d,f'{value} = unary_value({node.operator!r}, {operand})')
            elif kind is ast.Binary and node.operator in ('+','-','*','/','%','=','<>','<','<=','>','>=','AND','OR'):
                left=expr(node.left,d)
                if node.operator in ('AND','OR'):
                    emit(d,f'{value} = boolean({left})')
                    emit(d,f'if {"not " if node.operator == "OR" else ""}{value}:')
                    right=expr(node.right,d+1);emit(d+1,f'{value} = boolean({right})')
                else:
                    right=expr(node.right,d)
                    if node.operator in ('+','-','*'):
                        emit(d,f'if type({left}) is Decimal and type({right}) is Decimal:')
                        emit(d+1,f'{value} = {left} {node.operator} {right}')
                        emit(d,'else:');emit(d+1,f'{value} = binary_values({node.operator!r}, {left}, {right})')
                    else:emit(d,f'{value} = binary_values({node.operator!r}, {left}, {right})')
            elif kind is ast.Conditional:
                condition=expr(node.condition,d);emit(d,f'if boolean({condition}):')
                yes=expr(node.when_true,d+1);emit(d+1,f'{value} = {yes}')
                emit(d,'else:');no=expr(node.when_false,d+1);emit(d+1,f'{value} = {no}')
            else:raise Ineligible('opaque expression')
            return value
        return boundary(node,depth,produce)
    def statement(node, depth):
        kind=syntax_kind(node)
        def produce(d):
            nonlocal loop_depth
            # Nested block expression values must not become a module result.
            emit(d,'result = None')
            if kind is ast.ExpressionStatement:
                value=expr(node.expression,d);emit(d,f'result = {value}')
            elif kind is ast.Assign and syntax_kind(node.target) is ast.Name:
                value=expr(node.value,d);key=name(node.target.name,write=True)
                emit(d,f'storage[{key!r}] = {value}');known.add(key)
            elif kind is ast.Var:
                if node.execution_context == 'server':raise Ineligible('server declaration')
                for raw in node.names:
                    key=name(raw,write=True);emit(d,f'storage.setdefault({key!r}, None)');known.add(key)
            elif kind is ast.Routine:
                # execute_program has already published and validated declarations.
                emit(d,'pass')
            elif kind is ast.Return:
                value=expr(node.value,d) if node.value is not None else 'None'
                emit(d,f'raise ModuleReturn({value})')
            elif kind is ast.Try:
                before=set(known)
                emit(d,'try:');emit(d+1,'pass')
                for child in node.body:statement(child,d+1)
                body_known=set(known);known.clear();known.update(before)
                emit(d,'except ModuleRuntimeError as handled_error:')
                emit(d+1,'for handled_index in range(len(vm._handled_errors)):')
                emit(d+2,'vm._handled_errors[handled_index] = None')
                emit(d+1,'vm._handled_errors.append(handled_error)')
                emit(d+1,'try:');emit(d+2,'pass')
                for child in node.handler:statement(child,d+2)
                emit(d+1,'finally:');emit(d+2,'vm._handled_errors.pop()')
                known.intersection_update(body_known);emit(d,'result = None')
            elif kind is ast.If:
                before=set(known);exits=[];matched=temp();emit(d,f'{matched} = False')
                for condition,body in node.branches:
                    known.clear();known.update(before)
                    emit(d,f'if not {matched}:');test=expr(condition,d+1)
                    emit(d+1,f'if boolean({test}):');emit(d+2,f'{matched} = True')
                    for child in body:statement(child,d+2)
                    exits.append(set(known))
                known.clear();known.update(before)
                emit(d,f'if not {matched}:');emit(d+1,'pass')
                for child in node.otherwise:statement(child,d+1)
                exits.append(set(known));known.clear();known.update(set.intersection(*exits))
                emit(d,'result = None')
            elif kind in (ast.For,ast.While):
                if kind is ast.For:
                    first=expr(node.start,d);emit(d,f'{first} = require_number({first})')
                    last=expr(node.end,d);emit(d,f'{last} = require_number({last})')
                    key=name(node.name,write=True);emit(d,f'storage[{key!r}] = {first}');known.add(key)
                before=set(known);emit(d,'while True:')
                if kind is ast.For:emit(d+1,f'if not (require_number(storage[{key!r}]) <= {last}): break')
                else:
                    test=expr(node.condition,d+1);emit(d+1,f'if not boolean({test}): break')
                emit(d+1,'try:');emit(d+2,'pass');loop_depth+=1
                for child in node.body:statement(child,d+2)
                loop_depth-=1
                emit(d+1,'except ModuleContinue:');emit(d+2,'pass')
                if kind is ast.For:emit(d+1,f'storage[{key!r}] = require_number(storage[{key!r}]) + ONE')
                known.intersection_update(before);emit(d,'result = None')
            elif kind is ast.Break and loop_depth:
                emit(d,'break')
            elif kind is ast.Continue and loop_depth:
                emit(d,'raise ModuleContinue()')
            else:raise Ineligible('unsupported module statement')
        boundary(node,depth,produce)
    for node in block:statement(node,1)
    emit(1,'return result')
    source='\n'.join(lines)+'\n'
    if len(source.encode('utf-8'))>min(100000,max_source_bytes):raise Ineligible('source budget')
    from .runtime import binary_values,unary_value,boolean,require_number,BSLRuntimeError,_Return
    class ModuleContinue(Exception):pass
    namespace={'nodes':tuple(nodes),'constants':tuple(constants),'Decimal':Decimal,'ONE':Decimal(1),
               'binary_values':binary_values,'unary_value':unary_value,'boolean':boolean,
               'require_number':require_number,'ModuleContinue':ModuleContinue,
               'ModuleRuntimeError':BSLRuntimeError,'ModuleReturn':_Return}
    exec(_CODE_CACHE.get(source),namespace)
    return PlainModule(block,namespace['lowered'],source,frozenset(required),frozenset(names),frozenset(writes))
