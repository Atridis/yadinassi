"""Preparation-only whole synchronous scalar routine translation.

This is not an execution-authority gate. The caller must establish immutable
admission, exact scalar bindings, trusted hooks/storage and absence of tracing
before entering function(vm, scope). No dynamic service boundary occurs inside.
"""
from dataclasses import dataclass, fields
from decimal import Decimal
from .syntax import ast
from .owned_syntax import is_owned, syntax_kind
from .compiled_inline import _CODE_CACHE
from .python_translation_collections import COLLECTION_TYPES, COLLECTION_METHODS, CollectionRegion

class Ineligible(Exception):
    pass

@dataclass(frozen=True)
class SyncRoutine:
    function: object
    parameters: tuple
    names: frozenset
    source: str
    nodes: tuple
    constants: tuple
    containers: tuple
    uses_collections: bool = False

    @property
    def source_bytes(self):
        return len(self.source.encode('utf-8'))

    @property
    def binding_count(self):
        return len(self.nodes)+len(self.constants)+len(self.containers)


def lower(routine, *, max_source_bytes=100000, max_function_bytes=100000,
          max_bindings=100000):
    if (not is_owned(routine) or syntax_kind(routine) is not ast.Routine
            or routine.is_async or routine.is_dual
            or any(not parameter.by_value for parameter in routine.parameters)):
        raise Ineligible('requires owned synchronous value-parameter routine')
    parameters=tuple(parameter.name.casefold() for parameter in routine.parameters)
    if len(set(parameters))!=len(parameters):raise Ineligible('duplicate parameter')
    return _lower(routine, routine.body, parameters, block_mode=False,
                  max_source_bytes=max_source_bytes,max_function_bytes=max_function_bytes,
                  max_bindings=max_bindings)


def lower_block(block, *, start=0, stop=None, max_source_bytes=100000,
                max_function_bytes=100000, max_bindings=100000):
    """Compile a closed statement range retaining its real admitted container.

    The caller proves live scalar inputs listed in plan.parameters. The result
    is (returned, value), distinguishing Return None from normal completion.
    """
    if not is_owned(block) or not isinstance(block,list):
        raise Ineligible('requires real owned block container')
    if stop is None:stop=len(block)
    if type(start) is not int or type(stop) is not int or not 0<=start<stop<=len(block):
        raise Ineligible('invalid or empty scalar statement range')
    selected=tuple(block[index] for index in range(start,stop))
    return _lower(block,selected,(),block_mode=True,max_source_bytes=max_source_bytes,
                  max_function_bytes=max_function_bytes,max_bindings=max_bindings)


def _lower(root, statements, parameters, *, block_mode, max_source_bytes,
           max_function_bytes, max_bindings):
    from .python_translation_collection_graph import acyclic
    if not acyclic(statements):raise Ineligible('potentially cyclic collection graph boundary')
    required=set(parameters)
    slots={name:'v'+str(index) for index,name in enumerate(parameters)}
    known=set(parameters);nodes=[];constants=[];containers=[];lines=[];loops=[];serial=0
    node_slots={};expression_depth=0;value_types={};variable_types={};uses_collections=False
    def emit(depth,text):
        if depth>32:raise Ineligible('control nesting budget')
        lines.append('    '*depth+text)
        if len(lines)>10000:raise Ineligible('source line budget')
    def temp():
        nonlocal serial
        serial+=1;return 't'+str(serial)
    def name(value):
        value=value.casefold()
        if value in ('thisobject','этотобъект'):raise Ineligible('receiver name')
        if value not in slots:slots[value]='v'+str(len(slots))
        return slots[value]
    def handle(node):
        key=id(node)
        if key not in node_slots:
            if len(nodes)+len(constants)+len(containers)>=max_bindings:raise Ineligible('binding budget')
            node_slots[key]=len(nodes);nodes.append(node)
        return f'nodes[{node_slots[key]}]'
    def locate(node,depth):emit(depth,f'current = {handle(node)}')
    def expr(node,depth):
        nonlocal expression_depth
        expression_depth+=1
        try:
            if expression_depth>128:raise Ineligible('expression depth budget')
            return emit_expression(node,depth)
        finally:expression_depth-=1
    def emit_expression(node,depth):
        kind=syntax_kind(node);value=temp()
        if kind is ast.Literal and any(type(node.value) is scalar for scalar in (Decimal,bool,str,type(None))):
            if len(nodes)+len(constants)+len(containers)>=max_bindings:raise Ineligible('binding budget')
            constants.append(node.value);emit(depth,f'{value} = constants[{len(constants)-1}]')
        elif kind is ast.Name:
            if node.name.casefold() not in known:
                if not block_mode:raise Ineligible('read before definite initialization')
                required.add(node.name.casefold());known.add(node.name.casefold())
            emit(depth,f'{value} = {name(node.name)}');value_types[value]=variable_types.get(node.name.casefold())
        elif kind is ast.New:
            if node.name.casefold() not in COLLECTION_TYPES:raise Ineligible('unsupported collection constructor')
            args=[expr(argument,depth) for argument in node.arguments]
            value_types[value]=node.name.casefold()
            locate(node,depth);emit(depth,f'{value} = collections.new({node.name!r}, [{", ".join(args)}])')
        elif kind is ast.Call and syntax_kind(node.callee) is ast.Attribute:
            if node.callee.name.casefold() not in COLLECTION_METHODS:raise Ineligible('unsupported collection method')
            if node.callee.name.casefold() in ('property','свойство') and len(node.arguments)>1:raise Ineligible('by-reference property output boundary')
            receiver=expr(node.callee.object,depth)
            bound=temp();locate(node.callee.object,depth);emit(depth,f'{bound} = collections.bind({receiver}, {node.callee.name!r})')
            args=[expr(argument,depth) for argument in node.arguments]
            locate(node,depth);emit(depth,f'{value} = collections.invoke({bound}, [{", ".join(args)}])')
        elif kind is ast.Index:
            receiver=expr(node.object,depth);locate(node,depth)
            emit(depth,f'collections.prepare_index({receiver})')
            index=expr(node.index,depth)
            locate(node,depth);emit(depth,f'{value} = collections.read_index({receiver}, {index})')
        elif kind is ast.Attribute:
            receiver=expr(node.object,depth);locate(node,depth)
            if value_types.get(receiver) not in ('structure','структура','pair'):raise Ineligible('first-class member boundary')
            emit(depth,f'{value} = collections.read_attribute({receiver}, {node.name!r})')
        elif kind is ast.Group:
            value=expr(node.expression,depth)
        elif kind is ast.Unary and node.operator in ('+','-','NOT'):
            operand=expr(node.operand,depth);locate(node,depth)
            emit(depth,f'{value} = unary({node.operator!r}, {operand})')
        elif kind is ast.Binary and node.operator in ('+','-','*','/','%','=','<>','<','<=','>','>=','AND','OR'):
            left=expr(node.left,depth)
            if node.operator in ('AND','OR'):
                locate(node,depth);emit(depth,f'{value} = boolean({left})')
                emit(depth,f'if {"not " if node.operator == "OR" else ""}{value}:')
                right=expr(node.right,depth+1);locate(node,depth+1)
                emit(depth+1,f'{value} = boolean({right})')
            else:
                right=expr(node.right,depth);locate(node,depth)
                if node.operator in ('+','-','*'):
                    emit(depth,f'if type({left}) is Decimal and type({right}) is Decimal:')
                    emit(depth+1,f'{value} = {left} {node.operator} {right}')
                    emit(depth,'else:')
                    emit(depth+1,f'{value} = {binary_call(node.operator,left,right)}')
                else:emit(depth,f'{value} = {binary_call(node.operator,left,right)}')
        elif kind is ast.Conditional:
            test=expr(node.condition,depth);locate(node,depth)
            emit(depth,f'if boolean({test}):')
            yes=expr(node.when_true,depth+1);emit(depth+1,f'{value} = {yes}')
            emit(depth,'else:')
            no=expr(node.when_false,depth+1);emit(depth+1,f'{value} = {no}')
        else:raise Ineligible('non-scalar expression')
        return value
    def binary_call(operator,left,right):
        if uses_collections:return f'collections.binary({operator!r}, {left}, {right}, binary)'
        return f'binary({operator!r}, {left}, {right})'
    def increment(loop,depth):
        if loop is None:return
        node,counter=loop;locate(node,depth)
        emit(depth,f'{counter} = require_number({counter}) + ONE')
    def invalidate_loop_assignments(block):
        # A later iteration may enter with a different receiver kind. Do not
        # promise a Structure property where it could be a method value instead.
        pending=list(block)
        while pending:
            item=pending.pop()
            if isinstance(item,ast.Node):
                if syntax_kind(item) is ast.Assign and syntax_kind(item.target) is ast.Name:
                    variable_types[item.target.name.casefold()]=None
                for field in fields(item):
                    if field.name!='token':pending.append(getattr(item,field.name))
            elif isinstance(item,(tuple,list)):pending.extend(item)
    def sequence(block,depth):
        if not block:emit(depth,'pass')
        for node in block:statement(node,depth)
    def statement(node,depth):
        kind=syntax_kind(node)
        if kind is ast.Assign and syntax_kind(node.target) is ast.Name:
            value=expr(node.value,depth);emit(depth,f'{name(node.target.name)} = {value}')
            known.add(node.target.name.casefold());variable_types[node.target.name.casefold()]=value_types.get(value)
        elif kind is ast.Assign and syntax_kind(node.target) in (ast.Index,ast.Attribute):
            target=node.target;receiver=expr(target.object,depth);locate(node,depth)
            if syntax_kind(target) is ast.Index:emit(depth,f'collections.prepare_index({receiver}, write=True)')
            else:emit(depth,f'collections.prepare_attribute({receiver}, {target.name!r}, write=True)')
            index=expr(target.index,depth) if syntax_kind(target) is ast.Index else repr(target.name)
            value=expr(node.value,depth);locate(node,depth)
            operation='write_index' if syntax_kind(target) is ast.Index else 'write_attribute'
            emit(depth,f'collections.{operation}({receiver}, {index}, {value})')
        elif kind is ast.ExpressionStatement:
            expr(node.expression,depth)
        elif kind is ast.Var:
            emit(depth,'pass')
            for key in node.names:
                key=key.casefold();slot=name(key)
                # Conditional earlier assignment may already have created a slot.
                emit(depth,f'if {slot} is UNSET: {slot} = None');known.add(key)
        elif kind is ast.Return:
            value=expr(node.value,depth) if node.value is not None else 'None'
            emit(depth,f'return (True, {value})' if block_mode else f'return {value}')
        elif kind is ast.If:
            before=set(known);branch_types=dict(variable_types);type_exits=[];exits=[];matched=temp();emit(depth,f'{matched} = False')
            for condition,body in node.branches:
                known.clear();known.update(before);variable_types.clear();variable_types.update(branch_types)
                emit(depth,f'if not {matched}:')
                test=expr(condition,depth+1);locate(node,depth+1)
                emit(depth+1,f'if boolean({test}):');emit(depth+2,f'{matched} = True')
                sequence(body,depth+2);exits.append(set(known));type_exits.append(dict(variable_types))
            known.clear();known.update(before);variable_types.clear();variable_types.update(branch_types)
            emit(depth,f'if not {matched}:');sequence(node.otherwise,depth+1)
            exits.append(set(known));known.clear();known.update(set.intersection(*exits));type_exits.append(dict(variable_types))
            variable_types.clear();variable_types.update({key:value for key,value in branch_types.items() if all(exit.get(key)==value for exit in type_exits)})
        elif kind is ast.ForEach:
            source=expr(node.collection,depth);locate(node,depth)
            iterator=temp();emit(depth,f'{iterator} = collections.iterate({source})')
            before=set(known);loop_types=dict(variable_types);invalidate_loop_assignments(node.body);counter=name(node.name);known.add(node.name.casefold())
            variable_types[node.name.casefold()]='pair' if value_types.get(source) in ('map','соответствие','structure','структура') else None
            emit(depth,'while True:')
            emit(depth+1,'if lease is not None: lease.backedge()')
            locate(node,depth+1);emit(depth+1,'try:')
            emit(depth+2,f'{counter} = next({iterator})')
            emit(depth+1,'except StopIteration: break')
            loops.append(None);sequence(node.body,depth+1);loops.pop()
            known.intersection_update(before)
            variable_types.update({key:old if variable_types.get(key)==old else None for key,old in loop_types.items()})
        elif kind in (ast.For,ast.While):
            loop=None
            if kind is ast.For:
                first=expr(node.start,depth);locate(node,depth)
                emit(depth,f'{first} = require_number({first})')
                last=expr(node.end,depth);locate(node,depth)
                emit(depth,f'{last} = require_number({last})')
                counter=name(node.name);emit(depth,f'{counter} = {first}')
                known.add(node.name.casefold());loop=(node,counter)
            before=set(known);loop_types=dict(variable_types);invalidate_loop_assignments(node.body);emit(depth,'while True:');emit(depth+1,'if lease is not None: lease.backedge()')
            if kind is ast.For:
                locate(node,depth+1)
                emit(depth+1,f'if not (require_number({counter}) <= {last}): break')
            else:
                test=expr(node.condition,depth+1);locate(node,depth+1)
                emit(depth+1,f'if not boolean({test}): break')
            loops.append(loop);sequence(node.body,depth+1);loops.pop()
            increment(loop,depth+1);known.intersection_update(before)
            variable_types.update({key:old if variable_types.get(key)==old else None for key,old in loop_types.items()})
        elif kind is ast.Break:
            if not loops:raise Ineligible('break outside loop')
            emit(depth,'break')
        elif kind is ast.Continue:
            if not loops:raise Ineligible('continue outside loop')
            increment(loops[-1],depth);emit(depth,'continue')
        else:raise Ineligible('non-scalar statement')
    # Authority inventory is independent of the compact error-location register:
    # names/literals/declarations are consumed too, even if they cannot fail.
    if block_mode:
        if max_bindings<1:raise Ineligible('binding budget')
        containers.append(root)
    pending=list(statements) if block_mode else [root]
    seen={id(root)} if block_mode else set()
    while pending:
        value=pending.pop()
        if id(value) in seen:continue
        if isinstance(value,ast.Node):
            seen.add(id(value));handle(value)
            for field in fields(value):
                if field.name=='token' or (syntax_kind(value) is ast.Literal and field.name=='value'):continue
                pending.append(getattr(value,field.name))
        elif isinstance(value,(list,tuple)):
            if is_owned(value):
                if len(nodes)+len(constants)+len(containers)>=max_bindings:raise Ineligible('binding budget')
                containers.append(value)
            seen.add(id(value));pending.extend(value)
    uses_collections=any(syntax_kind(node) in (ast.New,ast.Call,ast.Index,ast.Attribute,ast.ForEach) for node in nodes)
    sequence(statements,2)
    emit(2,'return (False, None)' if block_mode else 'return None')
    if block_mode:parameters=tuple(sorted(required))
    body=lines;lines=[]
    emit(0,'def translated_sync(vm, scope, lease=None):')
    emit(1,f'current = {handle(statements[0] if block_mode else root)}')
    for key,slot in slots.items():
        emit(1,f'{slot} = scope[{key!r}]' if key in parameters else f'{slot} = scope.get({key!r}, UNSET)')
    if uses_collections:emit(1,'collections = CollectionRegion(lease)')
    emit(1,'_published = False');emit(1,'try:');lines.extend(body)
    def publish(depth):
        for key,slot in slots.items():
            emit(depth,f'if {slot} is not UNSET:')
            emit(depth+1,f'if lease is None: scope[{key!r}] = {slot}')
            emit(depth+1,f'else: lease.publish({key!r}, {slot})')
        if not slots:emit(depth,'pass')
    emit(1,'except BaseException as error:')
    emit(2,'if lease is not None: lease.check()')
    emit(2,'_published = True');publish(2)
    emit(2,'converted = vm.compiled_exception(current, error)')
    emit(2,'if converted is error: raise')
    emit(2,'raise converted from None')
    emit(1,'finally:');emit(2,'if not _published and (lease is None or lease.valid):')
    emit(3,'if lease is not None: lease.check()')
    emit(3,'_published = True');publish(3)
    source='\n'.join(lines)+'\n'
    if len(source.encode())>min(max_source_bytes,max_function_bytes):raise Ineligible('source byte budget')
    from .python_translation_expressions import binary,unary
    from .python_translation_collections import _number as require_number
    def boolean(value):
        if type(value) is bool:return value
        if type(value) is Decimal:return value != 0
        raise TypeError('Ожидается булево значение или число')
    def unary(operator,value):
        if operator == 'NOT':return not boolean(value)
        value=require_number(value)
        return value if operator == '+' else value.copy_negate()
    namespace={'nodes':tuple(nodes),'constants':tuple(constants),'Decimal':Decimal,
               'ONE':Decimal(1),'UNSET':object(),'binary':binary,'unary':unary,
               'boolean':boolean,'require_number':require_number,'CollectionRegion':CollectionRegion}
    try:exec(_CODE_CACHE.get(source),namespace)
    except (SyntaxError,RecursionError) as error:raise Ineligible('Python compilation budget') from error
    return SyncRoutine(namespace['translated_sync'],parameters,frozenset(slots),source,tuple(nodes),tuple(constants),tuple(containers),uses_collections)
