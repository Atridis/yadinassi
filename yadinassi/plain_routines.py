"""Narrow whole-routine research lowering, after live runtime admission.

Only immutable owned synchronous Val Decimal routines; opaque or policy-owned
execution remains on the existing compiled adapter. Not a Python sandbox.
"""
from dataclasses import dataclass
from decimal import Decimal
from .syntax import ast
from .owned_syntax import syntax_kind, OwnedList
from .compiled_inline import _CODE_CACHE

class Ineligible(Exception): pass

@dataclass(frozen=True)
class PlainRoutine:
    function: object
    parameters: tuple
    names: frozenset
    source: str
    generator: bool = False
    prefix_only: bool = False
    segments: tuple = ()


def lower(routine, *, max_source_bytes=100000, _start=0, _entry=None, _state=None):
    if _state is None:_state={'count':0,'remaining':min(100000,max_source_bytes)}
    _state['count']+=1
    if _state['count']>16:raise Ineligible()
    routine_body=routine.body[_start:]
    if (syntax_kind(routine) is not ast.Routine
            or routine.is_async or routine.is_dual
            or any(not p.by_value for p in routine.parameters)):
        raise Ineligible()
    parameters=tuple(p.name.casefold() for p in routine.parameters) if _entry is None else tuple(_entry)
    if len(set(parameters))!=len(parameters):raise Ineligible()
    slots={name:'v'+str(i) for i,name in enumerate(parameters)}
    known=set(parameters);constants=[];nodes=[];lines=[];serial=0;loops=[];generator=False
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
            elif kind is ast.Literal and any(type(node.value) is scalar for scalar in (Decimal, bool, str, type(None))):
                constants.append(node.value);emit(d,f'{value} = constants[{len(constants)-1}]')
            elif kind is ast.Group:
                operand=expr(node.expression,d);emit(d,f'{value} = {operand}')
            elif kind is ast.Unary and node.operator in ('+', '-', 'NOT'):
                operand=expr(node.operand,d)
                emit(d,f'{value} = unary_value({node.operator!r}, {operand})')
            elif kind is ast.Conditional:
                condition=expr(node.condition,d)
                emit(d,f'if boolean({condition}):')
                yes=expr(node.when_true,d+1);emit(d+1,f'{value} = {yes}')
                emit(d,'else:')
                no=expr(node.when_false,d+1);emit(d+1,f'{value} = {no}')
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
                        emit(d,'else:')
                        emit(d+1,f'{value} = binary_values({node.operator!r}, {left}, {right})')
                    else:emit(d,f'{value} = binary_values({node.operator!r}, {left}, {right})')
            else:raise Ineligible()
            return value
        return boundary(node,depth,produce)
    def statement(node,depth):
        nonlocal generator
        kind=syntax_kind(node)
        def produce(d):
            nonlocal generator
            if kind is ast.Var:
                emit(d,'pass')  # Redeclaring an existing slot is a legal no-op.
                for name in node.names:
                    key=name.casefold()
                    if key not in known:
                        emit(d,f'{slot(key)} = None');known.add(key)
            elif kind is ast.Assign and syntax_kind(node.target) is ast.Name:
                value=expr(node.value,d);name=node.target.name.casefold()
                emit(d,f'{slot(name)} = {value}');known.add(name)
            elif kind is ast.Return:
                if node.value is None:
                    emit(d,'return None')
                    return
                if syntax_kind(node.value) is ast.Call and node is routine_body[-1] and depth == 1:
                    # Only terminal calls: no detached local computation resumes.
                    # Include conditionally initialized slots, without inventing
                    # locals on branches which did not assign them.
                    generator=True
                    emit(d, "vm._compiled().stats['plain_call_adapter_boundaries'] = vm._compiled().stats.get('plain_call_adapter_boundaries', 0) + 1")
                    for name, storage in slots.items():
                        emit(d,f'if {storage!r} in locals(): vm.locals[{name!r}] = {storage}')
                    index=len(nodes);nodes.append(node.value)
                    emit(d,f'return (yield from vm._visit(nodes[{index}]))')
                else:
                    value=expr(node.value,d);emit(d,f'return {value}')
            elif kind is ast.If:
                before=set(known);exits=[]
                matched=temp();emit(d,f'{matched} = False')
                for condition,body in node.branches:
                    known.clear();known.update(before)
                    emit(d,f'if not {matched}:')
                    test=expr(condition,d+1);emit(d+1,f'if boolean({test}):')
                    emit(d+2,f'{matched} = True')
                    for child in body:statement(child,d+2)
                    exits.append(set(known))
                known.clear();known.update(before)
                emit(d,f'if not {matched}:');emit(d+1,'pass')
                for child in node.otherwise:statement(child,d+1)
                exits.append(set(known));known.clear();known.update(set.intersection(*exits))
            elif kind in (ast.For,ast.While):
                if kind is ast.For:
                    first=expr(node.start,d);emit(d,f'{first} = require_number({first})')
                    last=expr(node.end,d);emit(d,f'{last} = require_number({last})')
                    counter=slot(node.name)
                    emit(d,f'{counter} = {first}');known.add(node.name.casefold())
                before=set(known)
                emit(d,'while True:')
                if kind is ast.For:emit(d+1,f'if not (require_number({counter}) <= {last}): break')
                else:
                    test=expr(node.condition,d+1);emit(d+1,f'if not boolean({test}): break')
                emit(d+1,'try:');emit(d+2,'pass');loops.append(kind)
                for child in node.body:statement(child,d+2)
                loops.pop()
                emit(d+1,'except PlainContinue:');emit(d+2,'pass')
                if kind is ast.For:emit(d+1,f'{counter} = require_number({counter}) + ONE')
                known.intersection_update(before)
            elif kind is ast.Break:
                if not loops:raise Ineligible()
                emit(d,'break')
            elif kind is ast.Continue:
                if not loops:raise Ineligible()
                emit(d,'raise PlainContinue()')
            else:raise Ineligible()
        boundary(node,depth,produce)
    lines.append('def lowered(vm, '+', '.join(slots.values())+'):')
    # Labels require the original block-PC dispatcher. Never split that scope.
    has_labels=any(syntax_kind(item) is ast.Label for item in routine.body)
    suffix=None;prefix_only=False;next_plan=None
    for index,node in enumerate(routine_body):
        saved=(len(lines),len(constants),len(nodes),dict(slots),set(known),serial,generator,list(loops))
        try:statement(node,1)
        except Ineligible:
            if has_labels or (index == 0 and len(routine_body)==1):raise
            count,nconstants,nnodes,oldslots,oldknown,serial,generator,oldloops=saved
            del lines[count:];del constants[nconstants:];del nodes[nnodes:]
            slots.clear();slots.update(oldslots);known.clear();known.update(oldknown);loops[:]=oldloops
            # Transfer once: no detached Python computation after opaque effects.
            # The suffix remains a compiled adapter and is separately counted.
            suffix=tuple(routine_body[index:]);prefix_only=True;generator=True
            live=set(slots)
            def stored_names(value):
                kind=syntax_kind(value)
                if kind is ast.Assign and syntax_kind(value.target) is ast.Name:live.add(value.target.name.casefold())
                elif kind is ast.Var:live.update(n.casefold() for n in value.names)
                elif kind is ast.For:live.add(value.name.casefold())
                if kind is ast.Routine or kind is ast.Literal:return
                if isinstance(value, ast.Node):
                    from dataclasses import fields
                    for field in fields(value):
                        if field.name!='token':stored_names(getattr(value,field.name))
                elif type(value) is tuple or type(value) is list or type(value) is OwnedList:
                    for child in value:stored_names(child)
            stored_names(node)
            if len(suffix)>1:
                try:next_plan=lower(routine,max_source_bytes=max_source_bytes,
                    _start=_start+index+1,_entry=sorted(live),_state=_state)
                except Ineligible:next_plan=None
            for key,name in slots.items():
                emit(1,f'if {name!r} in locals(): vm.locals[{key!r}] = {name}')
            emit(1, "vm._compiled().stats['plain_suffix_adapter_entries'] = vm._compiled().stats.get('plain_suffix_adapter_entries', 0) + 1")
            emit(1,'saved_frame = vm._compiled()._plain_scope_snapshot()')
            emit(1,'for suffix_index, suffix_node in enumerate(suffix):')
            emit(2,"vm._compiled().stats['plain_suffix_adapter_nodes'] = vm._compiled().stats.get('plain_suffix_adapter_nodes', 0) + 1")
            emit(2,'yield from vm._visit(suffix_node)')
            emit(2,'if suffix_index == 0 and next_plan is not None:')
            emit(3,'resumed = vm._compiled()._resume_plain_segment(routine, next_plan, saved_frame)')
            emit(3,'if resumed is not None:')
            emit(4,'resume_function, resume_values, resume_generator = resumed')
            emit(4,'resume_result = resume_function(vm, *resume_values)')
            emit(4,'if resume_generator: resume_result = yield from resume_result')
            emit(4,'return resume_result')
            emit(1,'return None')
            break
    emit(1,'return None')
    source='\n'.join(lines)+'\n'
    if len(source.encode())>_state['remaining']:raise Ineligible()
    _state['remaining']-=len(source.encode())
    from .runtime import binary_values, unary_value, boolean, require_number
    class PlainContinue(Exception): pass
    namespace={'nodes':tuple(nodes),'constants':tuple(constants),'ONE':Decimal(1),
               'suffix':suffix,'next_plan':next_plan,'routine':routine,'Decimal':Decimal,'binary_values':binary_values,'unary_value':unary_value,
               'boolean':boolean,'require_number':require_number,'PlainContinue':PlainContinue}
    exec(_CODE_CACHE.get(source),namespace)
    segments=() if next_plan is None else (next_plan,)+next_plan.segments
    accounted_source=source if next_plan is None else source+next_plan.source
    return PlainRoutine(namespace['lowered'],parameters,frozenset(slots),accounted_source,generator,prefix_only,segments)
