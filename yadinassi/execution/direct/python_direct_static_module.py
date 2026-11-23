"""Compile-owned closed scalar/array/map regions, never cached runtime authority.

Compile-time numeric/array facts eliminate dispatch. General module locals and
dynamic boundary synchronization are emitted separately; source-owned profiles
retain their authority protocols. No runtime admission or generic graph scan.
"""
from decimal import Decimal
from yadinassi.syntax import ast as bsl

class _Decline(Exception):pass


OTHERWISE=object()


def _ungroup(node):
    while type(node) is bsl.Group:
        node = node.expression
    return node


def _invariant_digit(node):
    """Integral arithmetic whose successful values cannot vary with Decimal Emax."""
    node = _ungroup(node)
    if type(node) is bsl.Literal and type(node.value) is Decimal:
        coefficient = node.value.as_tuple()
        if coefficient.exponent == 0 and len(coefficient.digits) == 1:
            return int(node.value)
    if type(node) is bsl.Binary and type(node.operator) is str and node.operator in ('+', '-', '*'):
        left = _invariant_digit(node.left)
        right = _invariant_digit(node.right)
        if left is not None and right is not None:
            value = left + right if node.operator == '+' else left - right if node.operator == '-' else left * right
            if -9 <= value <= 9:
                return value
    return None


def _simple_literal_boolean(node):
    """Total boolean subset for which the emitter may replace the test itself."""
    return _literal_boolean(node, extended=False)


def _literal_boolean(node, *, extended=True):
    """Prove the outcome of a successful test without dropping runtime diagnostics."""
    inverted = False
    node = _ungroup(node)
    while type(node) is bsl.Unary and type(node.operator) is str and node.operator == 'NOT':
        inverted = not inverted
        node = _ungroup(node.operand)
    if type(node) is bsl.Literal and type(node.value) is bool:
        value = node.value
    elif type(node) is bsl.Binary and type(node.operator) is str:
        op = node.operator
        if extended and op in ('AND', 'OR'):
            left = _literal_boolean(node.left)
            if left is None:
                return None  # The left might throw or change state before RHS.
            value = left if left == (op == 'OR') else _literal_boolean(node.right)
            return None if value is None else value != inverted
        left, right = _ungroup(node.left), _ungroup(node.right)
        if type(left) is bsl.Literal and type(right) is bsl.Literal:
            left, right = left.value, right.value
            kind = type(left)
            if kind is not type(right) or kind not in (bool, Decimal):
                return None
            if kind is Decimal and not (left.is_finite() and right.is_finite()):
                return None
        elif extended:
            left, right = _invariant_digit(left), _invariant_digit(right)
            if left is None or right is None:
                return None
            left, right = Decimal(left), Decimal(right)
        else:
            return None
        if op == '=':
            value = left == right
        elif op == '<>':
            value = left != right
        elif op in ('<', '<=', '>', '>='):
            from yadinassi.execution.codegen.experimental_naked_scalar_semantics import order
            value = order(left, right, op)
        else:
            return None
    else:
        return None
    return value != inverted


def ordered_if(node, *, literal_reachability, extended_reachability=True):
    """Yield every arm, its live test/body flags, and a proven boolean if any."""
    reaches=True
    for condition,body in node.branches:
        literal=_literal_boolean(condition,extended=extended_reachability) if reaches and literal_reachability else None
        yield condition,body,reaches,reaches and literal is not False,literal
        if literal is True:reaches=False
    yield OTHERWISE,node.otherwise,False,reaches,None


def table_schema_setup(program, start, table_name):
    """Locate explicit numeric descriptors on the table's top-level setup statements."""
    positions = {}
    for position in range(start, len(program)):
        statement = program[position]
        if type(statement) in (bsl.For, bsl.While, bsl.ForEach, bsl.If):
            break
        if type(statement) is not bsl.ExpressionStatement:
            continue
        call = statement.expression
        if (type(call) is not bsl.Call or len(call.arguments) != 2
                or type(call.callee) is not bsl.Attribute
                or call.callee.name.casefold() not in ('add', 'добавить')):
            continue
        columns = _ungroup(call.callee.object)
        if (type(columns) is not bsl.Attribute
                or columns.name.casefold() not in ('columns', 'колонки')):
            continue
        table = _ungroup(columns.object)
        description = _ungroup(call.arguments[1])
        if (type(table) is bsl.Name and table.name.casefold() == table_name
                and type(description) is bsl.New
                and description.name.casefold() in ('typedescription', 'описаниетипов')):
            positions[position] = id(call)
    return positions


def analyze(program, opaque_names=(), *, scalar_prefix=False, builtin_results=None, builtin_external_names=(), numeric_routines=None, address_routines=None, literal_reachability=False, module_declarations=False, table_prefix_origin=None, extended_reachability=True, extended_tests=None, schema_setup=None):
    builtin_results = builtin_results or {}
    kinds={};names=set();opaque=set(opaque_names)|{'thisobject','этотобъект'}
    checked=set();active=set()
    numeric_routines={} if numeric_routines is None else numeric_routines
    address_routines={} if address_routines is None else address_routines
    def require(condition):
        if not condition:raise _Decline
    schema_calls=() if schema_setup is None else frozenset(schema_setup[1].values())
    schema_cutoff=-1 if schema_setup is None else max(schema_setup[1])
    def column_description(node,env,call):
        inner=_ungroup(node)
        if type(inner) is bsl.Literal and inner.value is None:
            kind='default_column_type'
        else:
            require(id(call) in schema_calls and type(inner) is bsl.New and inner.name.casefold() in ('typedescription','описаниетипов'))
            require(1<=len(inner.arguments)<=2)
            name=_ungroup(inner.arguments[0])
            require(type(name) is bsl.Literal and type(name.value) is str
                    and name.value.strip().casefold() in ('number','число'))
            expression(inner.arguments[0],env)
            if len(inner.arguments)==2:
                q=_ungroup(inner.arguments[1])
                require(type(q) is bsl.New and q.name.casefold() in ('numberqualifiers','квалификаторычисла')
                        and len(q.arguments)<=2)
                require(all(expression(arg,env)=='number' for arg in q.arguments))
                kinds[id(q)]='numeric_column_type'
            kind='numeric_column_type'
        kinds[id(inner)]=kinds[id(node)]=kind

    def expression(node,env):
        k=type(node)
        if scalar_prefix or active:
            require(k in (bsl.Group,bsl.Literal,bsl.Name,bsl.Binary,bsl.Unary,bsl.Conditional)
                    or (k is bsl.Call and type(node.callee) is bsl.Name))
        if k is bsl.Group:kind=expression(node.expression,env)
        elif k is bsl.Literal:
            require(type(node.value) in (Decimal,bool,str));kind='number' if type(node.value) is Decimal else 'bool' if type(node.value) is bool else 'string'
        elif k is bsl.Name:
            require(node.name.casefold() in env);kind=env[node.name.casefold()]
        elif k is bsl.New:
            if table_prefix_origin is not None:require(node is table_prefix_origin)
            constructors={'array':'array','массив':'array','map':'map','соответствие':'map','valuetable':'table','таблицазначений':'table','valuelist':'valuelist','списокзначений':'valuelist'}
            require(node.name.casefold() in constructors and not node.arguments);kind=constructors[node.name.casefold()]
        elif k is bsl.Index:
            owner=expression(node.object,env);index=expression(node.index,env)
            require(owner in ('array','map','table','valuelist','row') and
                    (index in ('number','string') if owner=='row' else index=='number'))
            kind={'table':'row','valuelist':'item'}.get(owner,'number')
        elif k is bsl.Attribute:
            owner=expression(node.object,env);name=node.name.casefold()
            if owner=='table' and name in ('columns','колонки'):kind='columns'
            elif owner=='row':kind='number'
            elif owner=='item' and name in ('value','значение'):kind='number'
            else:raise _Decline
        elif k is bsl.Binary:
            left=expression(node.left,env);right=expression(node.right,env)
            op=node.operator.casefold()
            if op in ('+','-','*','/','%'):
                require(left==right and (left=='number' or op=='+' and left=='string'));kind=left
            elif op in ('=','<>','<','<=','>','>='):
                require(left==right and left in ('number','bool'));kind='bool'
            elif op in ('and','or','и','или'):
                require(left in ('number','bool') and right in ('number','bool'));kind='bool'
            else:raise _Decline
        elif k is bsl.Unary:
            operand=expression(node.operand,env)
            require(operand in ('number','bool'))
            kind='bool' if node.operator.casefold() in ('not','не') else 'number'
            if kind=='number':require(operand=='number')
        elif k is bsl.Conditional:
            require(expression(node.condition,env) in ('number','bool'))
            kind=expression(node.when_true,env);require(kind==expression(node.when_false,env))
        elif k is bsl.Call and type(node.callee) is bsl.Name:
            name=node.callee.name.casefold()
            if name in numeric_routines:
                routine=numeric_routines[name]
                require(name not in active and len(node.arguments)<=len(routine.parameters))
                for i,parameter in enumerate(routine.parameters):
                    actual=node.arguments[i] if i<len(node.arguments) else None
                    if actual is None or type(actual) is bsl.OmittedArgument:
                        # Only substitute literal numeric defaults. In particular,
                        # do not move a signed Decimal operation before later actuals.
                        actual=parameter.default
                        require(type(actual) is bsl.Literal and type(actual.value) is Decimal)
                        require(expression(actual,{})=='number')
                    else:
                        require(expression(actual,env)=='number')
                if name not in checked:
                    active.add(name)
                    try:
                        local={p.name.casefold():'number' for p in routine.parameters}
                        for statement in routine.body[:-1]:
                            local[statement.target.name.casefold()]=expression(statement.value,local)
                        require(expression(routine.body[-1].value,local)=='number')
                    finally:active.remove(name)
                    checked.add(name)
                kind='number'
            else:
                kind=builtin_results.get(node.callee.name.casefold());require(kind is not None)
                for arg in node.arguments:
                    plain=arg
                    while type(plain) is bsl.Group:plain=plain.expression
                    # In a closed, guarded builtin unit the result does not depend
                    # on scalar argument type; external direct reads stay untouched.
                    if (type(plain) is bsl.Name and plain.name.casefold() not in env
                            and plain.name.casefold() in builtin_external_names):
                        continue
                    expression(arg,env)
        elif k is bsl.Call and type(node.callee) is bsl.Attribute and not scalar_prefix:
            receiver_kind=expression(node.callee.object,env);require(receiver_kind in ('array','map','table','valuelist','columns','row'))
            method=node.callee.name.casefold()
            if method in ('get','получить'):
                require(receiver_kind!='columns' and len(node.arguments)==1 and expression(node.arguments[0],env)=='number');kind={'table':'row','valuelist':'item'}.get(receiver_kind,'number')
            elif method in ('add','добавить'):
                if receiver_kind=='table':require(not node.arguments);kind='row'
                elif receiver_kind=='columns':
                    require(1<=len(node.arguments)<=2 and expression(node.arguments[0],env)=='string')
                    if len(node.arguments)==2:
                        require(extended_reachability)
                        column_description(node.arguments[1],env,node)
                    kind='column'
                elif receiver_kind=='valuelist':require(len(node.arguments)==1 and expression(node.arguments[0],env)=='number');kind='item'
                else:raise _Decline
            elif method in ('count','количество','ubound','вграница'):
                require(receiver_kind!='row' and not node.arguments and (receiver_kind=='array' or method in ('count','количество')));kind='number'
            elif method in ('total','итог'):
                require(receiver_kind=='table' and len(node.arguments)==1 and expression(node.arguments[0],env)=='string');kind='number'
            elif method in ('indexof','индекс'):
                argument_kind={'table':'row','columns':'column'}.get(receiver_kind)
                require(argument_kind is not None and len(node.arguments)==1 and expression(node.arguments[0],env)==argument_kind);kind='number'
            else:raise _Decline
        else:raise _Decline
        kinds[id(node)]=kind;return kind
    def assign(name,kind,env):
        key=name.casefold();require(key not in opaque)
        if key in env:require(env[key]==kind)
        env[key]=kind;names.add(key)
    def sequence(nodes,env):
        for node in nodes:
            k=type(node)
            if k is bsl.Routine and (numeric_routines or address_routines):continue
            if k is bsl.Var and table_prefix_origin is not None:continue
            if k is bsl.Assign:
                if scalar_prefix:require(type(node.target) is bsl.Name)
                kind=expression(node.value,env)
                if type(node.target) is bsl.Name:assign(node.target.name,kind,env)
                elif type(node.target) is bsl.Index:
                    require(expression(node.target.object,env) in ('array','map'))
                    require(expression(node.target.index,env)=='number' and kind=='number')
                    kinds[id(node.target)]='number'
                elif type(node.target) is bsl.Attribute:
                    owner=expression(node.target.object,env)
                    require(kind=='number' and (owner=='row' or owner=='item' and node.target.name.casefold() in ('value','значение')))
                    kinds[id(node.target)]='number'
                else:raise _Decline
            elif k is bsl.ExpressionStatement:
                call=node.expression
                if scalar_prefix:expression(call,env)
                elif type(call) is bsl.Call and type(call.callee) is bsl.Name and call.callee.name.casefold() in address_routines:
                    name=call.callee.name.casefold();routine=address_routines[name]
                    require(len(call.arguments)==len(routine.parameters))
                    for parameter,arg in zip(routine.parameters,call.arguments):
                        while type(arg) is bsl.Group:arg=arg.expression
                        if not parameter.by_value:
                            require(type(arg) is bsl.Index and expression(arg.object,env)=='array')
                        require(expression(arg,env)=='number')
                    if name not in checked:
                        active.add(name)
                        try:
                            local={p.name.casefold():'number' for p in routine.parameters}
                            for statement in routine.body:require(expression(statement.value,local)=='number')
                        finally:active.remove(name)
                        checked.add(name)
                    kinds[id(call)]='address_call'
                elif type(call) is bsl.Call and type(call.callee) is bsl.Attribute and call.callee.name.casefold() in ('add','добавить') and expression(call.callee.object,env)=='array':
                    require(expression(call.callee.object,env)=='array' and len(call.arguments)==1)
                    require(expression(call.arguments[0],env)=='number');kinds[id(call)]='append'
                elif type(call) is bsl.Call and type(call.callee) is bsl.Attribute and call.callee.name.casefold() in ('insert','вставить'):
                    require(expression(call.callee.object,env)=='map' and len(call.arguments)==2)
                    require(all(expression(arg,env)=='number' for arg in call.arguments));kinds[id(call)]='map_insert'
                else:expression(call,env)
            elif k is bsl.For:
                require(expression(node.start,env)=='number' and expression(node.end,env)=='number')
                assign(node.name,'number',env);nested=dict(env);sequence(node.body,nested)
                require(all(nested.get(key)==kind for key,kind in env.items()))
                kinds[id(node)]='number'  # The body preserves numeric induction.
            elif k is bsl.ForEach and not scalar_prefix:
                require(expression(node.collection,env)=='array')
                nested=dict(env);assign(node.name,'number',nested);sequence(node.body,nested)
                require(all(nested.get(key)==kind for key,kind in env.items()))
            elif k is bsl.While:
                require(expression(node.condition,env) in ('number','bool'))
                nested=dict(env);sequence(node.body,nested)
                require(all(nested.get(key)==kind for key,kind in env.items()))
            elif k is bsl.If:
                branches=[]
                for condition,body,live_test,live_body,literal in ordered_if(
                        node,literal_reachability=literal_reachability,extended_reachability=extended_reachability):
                    if extended_tests is not None and live_test and literal is not None and _simple_literal_boolean(condition) is None:
                        extended_tests.add(id(condition))
                    if live_test and literal is None:require(expression(condition,env) in ('number','bool'))
                    if live_body:
                        nested=dict(env);sequence(body,nested);branches.append(nested)
                merged={key:kind for key,kind in branches[0].items() if all(branch.get(key)==kind for branch in branches)}
                env.clear();env.update(merged)
            elif k in (bsl.Break,bsl.Continue):pass
            else:raise _Decline
        return env
    if scalar_prefix:
        # Reuse the existing transfer rules. An unknown statement is a
        # boundary for following code, never for an already proven prefix.
        env={}
        for node in program:
            committed=len(kinds)
            try:sequence((node,),env)
            except _Decline:
                while len(kinds)>committed:kinds.popitem()
                break
        return kinds
    if table_prefix_origin is not None:
        # Reuse the closed transfer rules, saving only successful top-level
        # statements; the first unproved statement and all successors stay generic.
        env={};prefix_kinds={}
        for index,node in enumerate(program):
            kinds={}
            try:sequence((node,),env)
            except _Decline:return index,prefix_kinds
            prefix_kinds.update(kinds)
            if index==schema_cutoff:
                # Ordinary construction may publish and rebind module slots.
                # Only the table itself is readmitted by the runtime schema guard.
                table_name=schema_setup[0]
                if env.get(table_name)!='table':return index,prefix_kinds
                env={table_name:'table'}
        return len(program),prefix_kinds
    # Declarations are still lowered into their original export and scheduler
    # entry points. They are not execution edges of a closed module body.
    if module_declarations:program=(node for node in program if type(node) is not bsl.Routine)
    try:sequence(program,{})
    except _Decline:return None
    if 'address_call' in kinds.values():
        if any(kind not in ('number','bool','string','array','append','address_call')
                                for kind in kinds.values()):return None
    return tuple(sorted(names)),kinds
