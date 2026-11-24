"""Clean-sheet direct emitter: Python owns control flow and scalar arithmetic."""
import ast as p
from decimal import Decimal
from types import FunctionType

from yadinassi.syntax import ast as b
from .experimental_naked_collections import Program, _host_omission_error, _host_omission_values
from .experimental_naked_scalar_semantics import TextAddend
from yadinassi.types.array_index import array_offset
from yadinassi.execution.direct.python_direct_plain_map import PlainMap, plain_map
from .experimental_naked_errors import handled_error, reraise_handled
from .experimental_naked_resources import bounded_array
from yadinassi.types.errors import BSLRuntimeError
from .experimental_naked_live_state import UNSET
from .experimental_naked_scalar_semantics import concatenate, presentation, truth
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported, REPAIRS
from yadinassi.execution.direct.python_direct_numbers import divide, remainder, sign
from yadinassi.execution.direct.python_direct_dynamic_new import construct
from yadinassi.execution.direct.python_direct_error_info import raise_arity_error, raise_error


_BINARY = {'+': p.Add, '-': p.Sub, '*': p.Mult}
_COMPARE = {'=': p.Eq, '<>': p.NotEq, '<': p.Lt, '<=': p.LtE, '>': p.Gt, '>=': p.GtE}
_MISSING = object()
_OP = dict(_Truth=truth, _Divide=divide, _Remainder=remainder, _Sign=sign,
           _String=concatenate, _Type=type, _Str=str, _Missing=_MISSING, _Unset=UNSET, _TextAddend=TextAddend, _Map=PlainMap, _NameError=NameError,
           _Recoverable=(ArithmeticError,TypeError,ValueError,IndexError,NameError,RecursionError,BSLRuntimeError),
           _Handled=handled_error, _Reraise=reraise_handled, _Raise=raise_error,
           _RaiseArity=raise_arity_error, _Presentation=presentation,
           _Construct=construct, _Array=bounded_array, _MapFrom=plain_map, _Omissions=_host_omission_values, _InvalidOmissions=_host_omission_error)


def member(context, receiver, key, count, want_value, omitted=()):
    folded=key.casefold()
    if not omitted and type(receiver) is list and folded in ('add','добавить') and count in (0,1):
        if want_value:
            raise TypeError('Процедура не возвращает значение: '+key)
        if count:
            return receiver.append
        return lambda: receiver.append(None)
    if not omitted and type(receiver) is PlainMap:
        if folded in ('insert','вставить') and count==2:return receiver.__setitem__
        if folded in ('get','получить') and count==1:return receiver.get
    return context.resolve_member_call(receiver,key,require_value=want_value,omitted=omitted)


_OP['_Member']=member
_OP['_Index']=lambda receiver, index: array_offset(receiver,index) if type(receiver) is list else index



def _node(n, token):
    if 'lineno' in n._attributes:
        n.lineno=n.end_lineno=token.line
        n.col_offset=max(0,token.column-1)
        n.end_col_offset=n.col_offset+1
    return n


def name(value, store=False):
    return p.Name(id=value, ctx=p.Store() if store else p.Load())


def call(target, *args, **kwargs):
    if isinstance(target,str):
        target=name(target)
    return p.Call(func=target, args=list(args),
                  keywords=[p.keyword(arg=k,value=v) for k,v in kwargs.items()])


def attr(target,key):
    return p.Attribute(value=target, attr=key, ctx=p.Load())


def literal(value):
    return p.Constant(value=value)


def arguments(names):
    return p.arguments(posonlyargs=[],args=[p.arg(arg=k) for k in names],vararg=None,
                       kwonlyargs=[],kw_defaults=[],kwarg=None,defaults=[])


def bind(template,state):
    # Helpers are closures, never Python names exposed through BSL state.
    # A compiled BSL global has no Python builtin fallback.
    old=dict.get(state,'__builtins__',_MISSING)
    dict.__setitem__(state,'__builtins__',{})
    try:
        return FunctionType(template.__code__,state,closure=template.__closure__)
    finally:
        if old is _MISSING:
            dict.__delitem__(state,'__builtins__')
        else:
            dict.__setitem__(state,'__builtins__',old)


class Emit:
    def __init__(self, filename):
        self.filename=filename
        self.number=0
        self.constants=[]
        self.loop=[]
        self.globals=set()
        self.written=set()
        self.locals=set()
        self.module_declarations=set()
        self.routines={}
        self.parameters={}

    def temp(self):
        self.number+=1
        return f'_T{self.number}'

    def var(self,key,store=False):
        key=key.casefold()
        if key not in self.locals:
            self.globals.add(key)
            if store:self.written.add(key)
        return name(key,store)

    def opaque(self,value):
        pos=len(self.constants)
        self.constants.append(value)
        return p.Subscript(value=name('_K'),slice=literal(pos),ctx=p.Load())

    def literal(self,value):
        if type(value) is Decimal:
            if value.as_tuple().exponent==0 and not (value.is_zero() and value.is_signed()):
                return literal(int(value))
            return self.opaque(value)
        if type(value) in (bool,str,type(None)):
            return literal(value)
        return self.opaque(value)

    def expr(self,x,want_value=True):
        return _node(self.expression(x,want_value),x.token)

    def expression(self,x,want_value):
        if type(x) is b.Literal:return self.literal(x.value)
        if type(x) is b.Name:return self.var(x.name)
        if type(x) is b.Group:return self.expr(x.expression,want_value)
        if type(x) is b.Conditional:
            return p.IfExp(test=self.condition(x.condition),
                           body=self.expr(x.when_true),orelse=self.expr(x.when_false))
        if type(x) is b.Unary:
            if x.operator=='NOT':return p.UnaryOp(op=p.Not(),operand=self.condition(x.operand))
            if type(x.operand) is b.Literal and type(x.operand.value) is Decimal:
                val=x.operand.value
                return self.literal(val.copy_negate() if x.operator=='-' else val)
            return call('_Sign',self.expr(x.operand),literal(x.operator))
        if type(x) is b.Binary:
            op=x.operator
            if op in ('AND','OR'):
                return p.BoolOp(op=p.And() if op=='AND' else p.Or(),
                                values=[self.condition(x.left),self.condition(x.right)])
            l,r=self.expr(x.left),self.expr(x.right)
            if op in _BINARY:
                if op=='+' and type(x.left) is b.Literal and type(x.left.value) is str:
                    return call('_String',l,r)
                return p.BinOp(left=l,op=_BINARY[op](),right=r)
            if op in _COMPARE:return p.Compare(left=l,ops=[_COMPARE[op]()],comparators=[r])
            if op=='/':return call('_Divide',l,r)
            if op=='%':return call('_Remainder',l,r)
        if type(x) is b.Index:
            return self.index(x,p.Load())
        if type(x) is b.Attribute:
            return call(attr(name('_C'),'get_member'),self.expr(x.object),literal(x.name))
        if type(x) is b.DynamicNew:
            params=literal(None) if x.parameters is None else self.expr(x.parameters)
            return call('_Construct',name('_C'),self.expr(x.type_expression),params)
        if type(x) is b.New:
            key=x.name.casefold()
            if key in ('array','массив','map','соответствие'):
                if self.omissions(x.arguments):
                    return call('_InvalidOmissions')
                if not x.arguments:
                    return p.List(elts=[],ctx=p.Load()) if key in ('array','массив') else call('_Map')
                return call('_Array' if key in ('array','массив') else '_MapFrom',
                            *(self.expr(arg) for arg in x.arguments))
            return self.service_call('new:'+key,x.arguments,want_value)
        if type(x) is b.Call and type(x.callee) in (b.Name,b.Attribute):
            c=x.callee
            if type(c) is b.Name:
                key=c.name.casefold()
                if key in self.routines:
                    return self.local_call(key,x.arguments)
                return self.service_call(c.name,x.arguments,want_value)
            omitted=self.omissions(x.arguments)
            args=[literal(None) if type(arg) is b.OmittedArgument else self.expr(arg)
                  for arg in x.arguments]
            binding=[] if not omitted else [literal(omitted)]
            bound=call('_Member',name('_C'),self.expr(c.object),literal(c.name),
                       literal(len(x.arguments)),literal(want_value),*binding)
            return call(bound,*args)
        raise PythonDirectUnsupported(f'clean emitter: {type(x).__name__}')

    @staticmethod
    def omissions(args):
        return tuple(i for i,arg in enumerate(args) if type(arg) is b.OmittedArgument)

    def local_call(self,key,args):
        bound=self.routines[key]
        omitted=self.omissions(args)
        if not omitted:
            return call(bound,*(self.expr(arg) for arg in args))
        # Only a call with a positional hole needs spelling its suffix by name.
        # CPython supplies exactly the same defaults as for a shortened call.
        params=self.parameters[key]
        if len(args)>len(params) or any(params[i].default is None for i in omitted):
            return call('_InvalidOmissions')
        prefix=omitted[0]
        return call(bound,*(self.expr(arg) for arg in args[:prefix]),
                    **{params[i].name.casefold():self.expr(args[i])
                       for i in range(prefix,len(args)) if i not in omitted})

    def service_call(self,key,args,want_value):
        omitted=self.omissions(args)
        resolver='resolve_optional_service' if omitted else 'resolve_service'
        bound=call(attr(name('_C'),resolver),literal(key),
                   require_value=literal(want_value),argument_count=literal(len(args)))
        if not omitted:
            return call(bound,*(self.expr(arg) for arg in args))
        slot=self.temp()
        prepared=p.NamedExpr(target=name(slot,True),
                             value=call('_Omissions',bound,literal(omitted),literal(len(args))))
        def item(obj,index):
            return p.Subscript(value=obj,slice=literal(index),ctx=p.Load())
        return call(item(prepared,0),*(item(item(name(slot),1),i)
            if i in omitted else self.expr(arg) for i,arg in enumerate(args)))

    def index(self,x,mode):
        slot=self.temp()
        receiver=p.NamedExpr(target=name(slot,True),value=self.expr(x.object))
        index=call('_Index',name(slot),self.expr(x.index))
        return _node(p.Subscript(value=receiver,slice=index,ctx=mode),x.token)

    def routine(self,routine):
        from dataclasses import fields
        if routine.execution_context!='client' or routine.is_dual or routine.is_async:
            raise PythonDirectUnsupported('clean emitter: nonlocal routine profile')
        if any(not param.by_value for param in routine.parameters):
            raise PythonDirectUnsupported('clean emitter: ByRef routine arguments')
        args=arguments(tuple(param.name.casefold() for param in routine.parameters))
        optional=False
        for param in routine.parameters:
            if param.default is not None:
                optional=True
                args.defaults.append(self.expr(param.default))
            elif optional:
                raise PythonDirectUnsupported('clean emitter: parameter after default')
        local={param.name.casefold() for param in routine.parameters}
        declared=set()
        writes=set()
        queue=[routine.body]
        while queue:
            item=queue.pop()
            if isinstance(item,b.Var):declared.update(key.casefold() for key in item.names)
            elif isinstance(item,b.Assign) and type(item.target) is b.Name:writes.add(item.target.name.casefold())
            elif isinstance(item,(b.For,b.ForEach)):writes.add(item.name.casefold())
            if isinstance(item,b.Node) and not isinstance(item,b.Literal):
                queue.extend(getattr(item,f.name) for f in fields(item) if f.name!='token')
            elif type(item) in (list,tuple):queue.extend(item)
        old_locals,old_globals=self.locals,self.globals
        self.locals=local|declared|(writes-self.module_declarations)
        self.globals=set()
        try:
            body=self.block(routine.body)
            if self.globals:body.insert(0,p.Global(names=sorted(self.globals)))
        finally:self.locals,self.globals=old_locals,old_globals
        return p.FunctionDef(name=self.routines[routine.name.casefold()],args=args,
                             body=body,decorator_list=[])

    def condition(self,x):
        root=x
        while type(root) is b.Group:root=root.expression
        value=self.expr(x)
        if (type(root) is b.Binary and root.operator in (*_COMPARE,'AND','OR')
                or type(root) is b.Unary and root.operator=='NOT'
                or type(root) is b.Literal and type(root.value) in (bool,Decimal)):
            return value
        return call('_Truth',value)

    def block(self,nodes):
        return [stmt for n in nodes for stmt in self.stmt(n)] or [p.Pass()]

    def stmt(self,n):
        return [_node(stmt,n.token) for stmt in self.statement(n)]

    def statement(self,n):
        kind=type(n)
        if kind is b.Assign:
            t=n.target
            value=self.expr(n.value)
            if type(t) is b.Name:target=self.var(t.name,True)
            elif type(t) is b.Index:
                target=self.index(t,p.Store())
            elif type(t) is b.Attribute:
                write=call(attr(name('_C'),'resolve_set_member'),self.expr(t.object),literal(t.name))
                return [p.Expr(value=call(write,value))]
            else:raise PythonDirectUnsupported('clean emitter: assignment target')
            return [p.Assign(targets=[target],value=value)]
        if kind is b.ExpressionStatement:return [p.Expr(value=self.expr(n.expression,want_value=False))]
        if kind is b.Var:
            if self.locals:
                return [p.Assign(targets=[self.var(k,True)],value=literal(None)) for k in n.names]
            return [p.Expr(value=call(attr(name('_S'),'setdefault'),literal(k.casefold()),literal(None))) for k in n.names]
        if kind is b.If:
            tail=self.block(n.otherwise)
            for condition,body in reversed(n.branches):
                tail=[p.If(test=self.condition(condition),body=self.block(body),orelse=tail)]
            return tail
        if kind in (b.While,b.ForEach,b.For):
            prefix=[]
            advance=None
            if kind is b.For:
                first,last=self.temp(),self.temp()
                prefix=[p.Assign(targets=[name(first,True)],value=self.expr(n.start)),
                        p.Assign(targets=[name(last,True)],value=self.expr(n.end)),
                        p.Assign(targets=[self.var(n.name,True)],value=name(first))]
                advance=p.AugAssign(target=self.var(n.name,True),op=p.Add(),value=literal(1))
                test=p.Compare(left=self.var(n.name),ops=[p.LtE()],comparators=[name(last)])
            elif kind is b.While:
                test=self.condition(n.condition)
            self.loop.append(advance)
            try:body=self.block(n.body)
            finally:self.loop.pop()
            if advance is not None:
                body.append(advance)
            if kind is b.ForEach:
                return [p.For(target=self.var(n.name,True),iter=self.expr(n.collection),body=body,orelse=[])]
            return prefix+[p.While(test=test,body=body,orelse=[])]
        if kind is b.Break:return [p.Break()]
        if kind is b.Continue:
            from copy import deepcopy
            prefix=[] if not self.loop or self.loop[-1] is None else [deepcopy(self.loop[-1])]
            return prefix+[p.Continue()]
        if kind is b.Try:
            caught=self.temp()
            note=call('_Handled',name('_C'),name(caught),literal(self.filename),name('_Source'))
            handler=p.With(items=[p.withitem(context_expr=note,optional_vars=None)],body=self.block(n.handler))
            return [p.Try(body=self.block(n.body),handlers=[p.ExceptHandler(type=name('_Recoverable'),name=caught,
                body=[handler])],orelse=[],finalbody=[])]
        if kind is b.Raise:
            if n.value is None:
                return [p.Expr(value=call('_Reraise',name('_C')))]
            description=call('_Presentation',self.expr(n.value))
            args=n.optional_arguments or ()
            if len(args)>4:
                return [p.Expr(value=call('_RaiseArity',description))]
            options=p.Tuple(elts=[literal(None) if type(arg) is b.OmittedArgument
                                  else self.expr(arg) for arg in args],ctx=p.Load())
            t=n.token
            return [p.Expr(value=call('_Raise',name('_C'),description,options,
                                      literal(self.filename),literal(t.line),
                                      literal(t.column),literal(t.source_line)))]
        if kind is b.Return:return [p.Return(value=literal(None) if n.value is None else self.expr(n.value))]
        raise PythonDirectUnsupported(f'clean emitter: {kind.__name__}')


def compile_module(vm,program,nodes,source_text,source_name,*,_exports=False):
    if _exports:
        raise PythonDirectUnsupported('clean emitter: standalone export bind')
    filename=source_name or (program[0].token.source if program else '<строка>')
    compiler=Emit(filename)
    routines=[node for node in program if type(node) is b.Routine]
    compiler.module_declarations=set(vm.module_names)|{
        key.casefold() for node in program if type(node) is b.Var for key in node.names}
    compiler.routines={node.name.casefold():compiler.temp() for node in routines}
    compiler.parameters={node.name.casefold():node.parameters for node in routines}
    defs=[compiler.routine(node) for node in routines]
    ordinary=[node for node in program if type(node) is not b.Routine]
    tail=bool(ordinary and type(ordinary[-1]) is b.ExpressionStatement)
    statements=ordinary[:-1] if tail else ordinary
    body=[stmt for node in statements for stmt in compiler.stmt(node)]
    body.append(p.Return(value=compiler.expr(ordinary[-1].expression,False) if tail else name('_S')))
    if compiler.globals:
        body.insert(0,p.Global(names=sorted(compiler.globals)))
    if routines:
        exports=p.Dict(keys=[literal(k) for k in compiler.routines],
                       values=[name(v) for v in compiler.routines.values()])
        body[:0]=[*defs,p.If(test=name('_Bind'),body=[p.Return(value=exports)],orelse=[])]
    entry=p.FunctionDef(name='naked_module',args=arguments(('_S','_K','_O','_C','_Bind')),
                        body=body,decorator_list=[])
    helpers={**_OP,'_Source':source_text or ''}
    helper_names=tuple(helpers)
    factory=p.FunctionDef(name='_factory',args=arguments(helper_names),
                          body=[entry,p.Return(value=name('naked_module'))],decorator_list=[])
    tree=p.fix_missing_locations(p.Module(body=[factory],type_ignores=[]))
    generated=p.unparse(entry)
    ns={}
    exec(compile(tree,filename,'exec'),ns)
    template=ns['_factory'](*helpers.values())
    published=tuple(compiler.written)
    def run(state,constants,output,context,bind_only=False):
        # Only the public observation uses Decimal. No conversion or
        # publication runs in the body of the generated loop.
        try:
            result=bind(template,state)(state,constants,output,context,bind_only)
            return Decimal(result) if type(result) is int else result
        finally:
            if not bind_only:
                for key in published:
                    value=state.get(key)
                    if type(value) is int:state[key]=Decimal(value)
    return Program(generated,tuple(compiler.constants),run,{},frozenset(REPAIRS),
                   source_name=filename,source_text=source_text or '',trusted_entry=True)
