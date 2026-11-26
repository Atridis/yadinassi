"""Routine parameters, default values, and generated local scope."""
import ast as p
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.syntax import ast as b
from .direct_reference_lowering import SELF_NAMES
from ..direct_collections import UnsupportedNakedSyntax
from ..direct_python_ast import _node, arguments, attr, call, literal, name


def routine(self,routine):
    from dataclasses import fields
    args=arguments(tuple(param.name.casefold() for param in routine.parameters))
    optional=False
    defaults=[]
    for param in routine.parameters:
        if param.default is not None:
            optional=True
            default=self.expr(param.default)
            key=param.name.casefold()
            if param.by_value:
                deferred = type(param.default) is not b.Literal
                args.defaults.append(name('_OmittedRef') if deferred else default)
                if deferred or self.source_dispatch:
                    defaults.append(p.If(test=p.Compare(left=name(key),ops=[p.Is()],comparators=[name('_OmittedRef')]),
                        body=[p.Assign(targets=[name(key,True)],value=default)],orelse=[]))
            else:
                args.defaults.append(name('_Missing'))
                probe=p.Compare(left=name(key),ops=[p.Is()],comparators=[name('_Missing')])
                if self.source_dispatch:
                    probe=p.BoolOp(op=p.Or(),values=[probe,p.Compare(left=name(key),ops=[p.Is()],comparators=[name('_OmittedRef')])])
                defaults.append(p.If(test=probe,
                    body=[p.Assign(targets=[name(key,True)],value=call('_Cell',default))],orelse=[]))
        elif optional:
            raise PythonDirectUnsupported('clean emitter: parameter after default')
    local={param.name.casefold() for param in routine.parameters}
    declared=set()
    writes=set()
    direct_vars=({id(statement) for statement in routine.body if type(statement) is b.Var}
                 if self.externals else ())
    queue=[routine.body]
    has_fragments=False
    has_await=False
    while queue:
        item=queue.pop()
        if type(item) is b.Await:has_await=True
        if type(item) is b.Execute or (type(item) is b.Call and type(item.callee) is b.Name
                and item.callee.name.casefold() in ('eval','вычислить')):
            has_fragments=True
        if isinstance(item,b.Var):
            keys={key.casefold() for key in item.names}
            if keys & self.externals and id(item) not in direct_vars:
                raise PythonDirectUnsupported('conditional local Var shadowing external storage')
            declared.update(keys)
        elif isinstance(item,b.Assign) and type(item.target) is b.Name:writes.add(item.target.name.casefold())
        elif isinstance(item,(b.For,b.ForEach)):writes.add(item.name.casefold())
        if isinstance(item,b.Node) and not isinstance(item,b.Literal):
            queue.extend(getattr(item,f.name) for f in fields(item) if f.name!='token')
        elif type(item) in (list,tuple):queue.extend(item)
    old=self.locals,self.globals,self.references,self.addresses,self.in_routine,self.shadows,self.in_async
    self.in_routine=True
    self.in_async=routine.is_async
    implicit=SELF_NAMES if self.current_module else frozenset()
    shadows=(writes & self.shadowable & self.externals)-self.module_declarations-declared-local
    if shadows and has_fragments:
        raise UnsupportedNakedSyntax('source implicit namespace shadow with Execute/Eval is not integrated')
    self.implicit_shadows.update(shadows)
    self.shadows=frozenset(shadows)
    self.locals=local|declared|shadows|(writes-self.module_declarations-self.externals-implicit)
    self.globals=set()
    self.references={param.name.casefold() for param in routine.parameters if not param.by_value}
    self.addresses={}
    try:
        body=self.block(routine.body)
        if self.scalar_routines:
            actuals=p.Tuple(elts=[call('_PublicNumber',name(param.name.casefold())) for param in routine.parameters],ctx=p.Load())
            body.insert(0,p.Expr(value=call(attr(name('_C'),'scalar_values'),actuals)))
        shadow_slots=[p.Assign(targets=[name(key,True)],value=name('_Unset')) for key in sorted(shadows)]
        body=[*self.address_definitions(),*defaults,*shadow_slots,*body]
        if self.globals and not self.fragment:body.insert(0,p.Global(names=sorted(self.globals)))
        if routine.is_async and not has_await:
            # A no-Await async routine is still started eagerly as a task.
            body.append(_node(p.If(test=literal(False),
                body=[p.Expr(value=p.Yield(value=None))],orelse=[]),routine.token))
    finally:self.locals,self.globals,self.references,self.addresses,self.in_routine,self.shadows,self.in_async=old
    body=body or [p.Pass()]
    if self.source_scopes:
        manager=call(attr(name('_C'),'routine_scope'))
        body=[p.With(items=[p.withitem(context_expr=manager,optional_vars=None)],body=body)]
    return p.FunctionDef(name=self.routines[routine.name.casefold()],args=args,
                         body=body,decorator_list=[])
