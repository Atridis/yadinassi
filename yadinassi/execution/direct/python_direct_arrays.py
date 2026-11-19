"""Small forward facts for native arrays; no cached values or runtime authority.

Unknown effects clear facts. Receiver identity and scalar contents are separate:
reading an opaque item can end scalar reasoning without losing the already-bound
receiver. Loop facts require one callback-free invariant body (no alias graph).
"""
import sys
from decimal import Decimal
from yadinassi.syntax import ast


def array_facts(program, *, opaque_names=(), routine_opaque=None, definite_reads=None):
    opaque=frozenset(name.casefold() for name in opaque_names)
    receivers=set();indexes=set()
    scalar={'nn','bounded','int','scalar'}
    arrays={'array','scalar_array'}
    aliases={'добавить':'add','получить':'get','количество':'count','вграница':'ubound','очистить':'clear'}

    def arguments(nodes,known,record):
        result=[]
        for node in nodes:
            value,pure=expr(node,known,record);result.append((value,pure))
            if not pure:known.clear()
        return result

    def expr(node,known,record):
        kind=type(node)
        if kind is ast.Group:return expr(node.expression,known,record)
        if kind is ast.Literal:
            v=node.value
            if type(v) is Decimal and v.is_finite() and v==v.to_integral_value():
                return ('nn' if 0<=v<=sys.maxsize else 'bounded' if -sys.maxsize<=v<=sys.maxsize else 'int'),True
            return ('scalar',True) if type(v) in (type(None),bool,str,Decimal) else (None,False)
        if kind is ast.Name:
            if record and definite_reads is not None and node.name.casefold() not in opaque and node.name.casefold() in known:
                definite_reads.add(id(node))
            return (None,False) if node.name.casefold() in opaque else (known.get(node.name.casefold()),True)
        if kind is ast.New:
            args=arguments(node.arguments,known,record)
            pure=all(p and t in scalar for t,p in args)
            if node.name.casefold() in ('array','массив') and pure:return ('scalar_array' if len(args)<=1 else 'array'),True
            return None,False
        if kind is ast.Index:
            receiver,pure=expr(node.object,known,record)
            if not pure:known.clear()
            index,ipure=expr(node.index,known,record)
            if receiver in arrays and index in scalar and pure and ipure:
                if record:
                    receivers.add(id(node))
                    if index=='nn':indexes.add(id(node))
                return ('scalar' if receiver=='scalar_array' else None),True
            return None,False
        if kind is ast.Call and type(node.callee) is ast.Attribute:
            receiver,pure=expr(node.callee.object,known,record)
            if not pure:known.clear()
            method=aliases.get(node.callee.name.casefold(),node.callee.name.casefold())
            args=arguments(node.arguments,known,record)
            valid=(method in ('count','ubound','clear') and not args or method=='add' and len(args)<=1 or method=='get' and len(args)==1)
            if receiver in arrays and pure and valid:
                if record:receivers.add(id(node))
                allpure=all(p for _,p in args)
                if method=='get':
                    if args[0][0] not in scalar:return None,False
                    if record and args[0][0]=='nn' and allpure:indexes.add(id(node))
                    return ('scalar' if receiver=='scalar_array' else None),allpure
                if method in ('count','ubound'):return ('nn' if method=='count' else 'int'),True
                if method=='clear' and receiver!='scalar_array':return None,False
                if method=='add' and args and args[0][0] not in scalar:
                    # Any alias can observe the new contents. Retain exact-list
                    # facts but conservatively drop scalar-content claims.
                    for name,value in list(known.items()):
                        if value=='scalar_array':known[name]='array'
                return 'scalar',allpure
            return None,False
        if kind is ast.Binary:
            left,lpure=expr(node.left,known,record)
            # A host-capable left operation can mutate names before the right.
            if not lpure or node.operator in ('AND','OR') and left not in scalar:known.clear()
            right,rpure=expr(node.right,known,record)
            if lpure and rpure and left in scalar and right in scalar:
                if node.operator in ('+','-','*','%') and left in ('nn','bounded','int') and right in ('nn','bounded','int'):
                    if left==right=='nn' and node.operator=='-':return 'bounded',True
                    if left==right=='nn' and node.operator=='%':return 'nn',True
                    return 'int',True
                return 'scalar',True
            return None,False
        if kind is ast.Unary:
            value,pure=expr(node.operand,known,record)
            return ('scalar',True) if pure and value in scalar else (None,False)
        return None,False

    def assigned(nodes):
        result=set()
        for node in nodes:
            if type(node) is ast.Assign and type(node.target) is ast.Name:result.add(node.target.name.casefold())
            if type(node) is ast.For:result.add(node.name.casefold());result.update(assigned(node.body))
            if type(node) is ast.If:
                for _,body in node.branches:result.update(assigned(body))
                result.update(assigned(node.otherwise or []))
        return result

    def block(nodes,incoming,record):
        known=dict(incoming);pure=True
        for node in nodes:
            kind=type(node)
            if kind is ast.Routine:continue
            if kind is ast.Assign and type(node.target) is ast.Name:
                value,ok=expr(node.value,known,record)
                key=node.target.name.casefold()
                if not ok or key in opaque:known.clear();pure=False
                if key in opaque:continue
                if value is None:known.pop(key,None)
                else:known[key]=value
            elif kind is ast.ExpressionStatement:
                _,ok=expr(node.expression,known,record)
                if not ok:known.clear();pure=False
            elif kind is ast.For:
                start,sp=expr(node.start,known,False)
                if not sp:known.clear()
                end,ep=expr(node.end,known,False)
                if not ep:known.clear()
                seed=dict(known);counter=node.name.casefold();seed[counter]='nn' if start=='nn' and end in ('nn','bounded') else 'int'
                writes=assigned(node.body)
                for name in writes-{counter}:
                    if seed.get(name) in scalar:seed[name]='scalar'
                output,bp=block(node.body,seed,False)
                invariant=all(output.get(name)==value or output.get(name) in scalar and value in scalar for name,value in seed.items() if name!=counter)
                if counter not in opaque and sp and ep and start in ('nn','bounded','int') and end in scalar and bp and invariant and counter not in assigned(node.body):
                    if record and definite_reads is not None:definite_reads.add(id(node))
                    expr(node.start,known,record);expr(node.end,known,record)
                    block(node.body,seed,record);known[counter]='int'
                    for name in writes-{counter}:
                        if known.get(name) in scalar:known[name]='scalar'
                else:known.clear();pure=False
            elif kind is ast.Var:
                pass  # Existing values are preserved; do not invent facts.
            else:known.clear();pure=False
        return known,pure

    block(program,{},True)
    if routine_opaque is not None:
        for routine in program:
            if type(routine) is ast.Routine and id(routine) in routine_opaque:
                # No parameter or caller facts cross a function boundary. Only
                # assignments in this body can establish native local values.
                opaque=frozenset(routine_opaque[id(routine)])
                block(routine.body,{},True)
    return frozenset(receivers),frozenset(indexes)
