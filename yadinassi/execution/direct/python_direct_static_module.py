"""Compile-owned closed scalar/array/map regions, never cached runtime authority.

Compile-time numeric/array facts eliminate dispatch. General module locals and
dynamic boundary synchronization are emitted separately; source-owned profiles
retain their authority protocols. No runtime admission or generic graph scan.
"""
from decimal import Decimal
from yadinassi.syntax import ast as bsl

class _Decline(Exception):pass


def analyze(program, opaque_names=(), *, scalar_prefix=False, builtin_results=None, builtin_external_names=(), numeric_routines=None):
    builtin_results = builtin_results or {}
    kinds={};names=set();opaque=set(opaque_names)|{'thisobject','этотобъект'}
    checked=set();active=set()
    numeric_routines={} if numeric_routines is None else numeric_routines
    def require(condition):
        if not condition:raise _Decline
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
                name=node.callee.name.casefold();routine=numeric_routines.get(name)
                require(routine is not None and name not in active and len(node.arguments)==len(routine.parameters))
                require(all(expression(arg,env)=='number' for arg in node.arguments))
                if name not in checked:
                    active.add(name)
                    try:
                        result=expression(routine.body[0].value,{p.name.casefold():'number' for p in routine.parameters})
                        require(result=='number')
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
                elif receiver_kind=='columns':require(len(node.arguments)==1 and expression(node.arguments[0],env)=='string');kind='column'
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
            if k is bsl.Routine and numeric_routines:continue
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
            elif k is bsl.While:
                require(expression(node.condition,env) in ('number','bool'))
                nested=dict(env);sequence(node.body,nested)
                require(all(nested.get(key)==kind for key,kind in env.items()))
            elif k is bsl.If:
                branches=[]
                for condition,body in node.branches:
                    require(expression(condition,env) in ('number','bool'))
                    nested=dict(env);sequence(body,nested);branches.append(nested)
                nested=dict(env);sequence(node.otherwise,nested);branches.append(nested)
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
    try:sequence(program,{})
    except _Decline:return None
    return tuple(sorted(names)),kinds
