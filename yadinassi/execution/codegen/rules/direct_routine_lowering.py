"""Routine parameters, default values, and generated local scope."""
import ast as p
from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.syntax import ast as b
from .direct_reference_lowering import SELF_NAMES
from ..direct_collections import UnsupportedNakedSyntax
from ..direct_python_ast import _node, arguments, attr, call, literal, name


def routine(self,routine):
    from dataclasses import fields
    slot_keys=self.routine_slot_keys[routine.name.casefold()]
    names=tuple(key for param in routine.parameters
                for key in ((param.name.casefold(),slot_keys[param.name.casefold()])
                            if not param.by_value else (param.name.casefold(),)))
    args=arguments(names)
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
                args.defaults.extend((name('_Missing'),literal(None)))
                probe=p.BoolOp(op=p.Or(),values=[
                    p.Compare(left=name(key),ops=[p.Is()],comparators=[name(marker)])
                    for marker in ('_Missing','_OmittedRef')])
                defaults.append(p.If(test=probe,
                    body=[p.Assign(targets=[name(key,True)],value=p.List(elts=[default],ctx=p.Load())),
                          p.Assign(targets=[name(slot_keys[key],True)],value=literal(0))],orelse=[]))
        elif optional:
            # Python requires a default for every later positional slot.
            # Both local and published BSL binders reject a missing required
            # position before evaluating actuals (test_defaults).
            args.defaults.append(name('_OmittedRef'))
            if not param.by_value: args.defaults.append(literal(None))
    local={param.name.casefold() for param in routine.parameters}
    declared=set()
    writes=set()
    direct_vars={id(statement) for statement in routine.body if type(statement) is b.Var}
    queue=[routine.body]
    has_fragments=False
    has_await=False
    has_goto=False
    borrowed=set()
    while queue:
        item=queue.pop()
        if type(item) is b.Call:
            callee=item.callee
            while type(callee) is b.Group:callee=callee.expression
            params=self.parameters.get(callee.name.casefold(),()) if type(callee) is b.Name else ()
            for formal, actual in zip(params,item.arguments):
                if not formal.by_value:
                    while type(actual) is b.Group:actual=actual.expression
                    if type(actual) is b.Name:borrowed.add(actual.name.casefold())
        if type(item) is b.Await:has_await=True
        if type(item) is b.Goto:has_goto=True
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
    old=self.locals,self.globals,self.references,self.addresses,self.in_routine,self.shadows,self.in_async,self.slot_keys,self.boxed_locals
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
    self.slot_keys=slot_keys
    self.boxed_locals={key:self.temp() for key in sorted(borrowed & self.locals-self.references-shadows)}
    try:
        boxes=[p.Assign(targets=[name(slot,True)],
                        value=p.Dict(keys=[literal(0)],values=[name(key)]) if key in local
                        else call('_LocalStorage',literal(key)))
               for key,slot in self.boxed_locals.items()]
        # Var declares storage, not a new assignment at its source position.
        # A preceding write must survive it (test_declared_local_retains_prior_value).
        initial=[]
        statements=routine.body
        # Keep declarations visible to the existing Goto cycle planner.
        if direct_vars and not has_goto:
            entry_locals=dict.fromkeys(key.casefold() for statement in statements
                                       if id(statement) in direct_vars for key in statement.names
                                       if key.casefold() not in local)
            initial=[p.Assign(targets=[self.var(key,True)],value=literal(None)) for key in entry_locals]
            statements=[statement for statement in statements if id(statement) not in direct_vars]
        body=self.block(statements)
        if self.scalar_routines:
            actuals=p.Tuple(elts=[call('_PublicNumber',name(param.name.casefold())) for param in routine.parameters],ctx=p.Load())
            body.insert(0,p.Expr(value=call(attr(name('_C'),'scalar_values'),actuals)))
        shadow_slots=[p.Assign(targets=[name(key,True)],value=name('_Unset')) for key in sorted(shadows)]
        body=[*self.address_definitions(),*defaults,*boxes,*shadow_slots,*initial,*body]
        if self.globals and not self.fragment:body.insert(0,p.Global(names=sorted(self.globals)))
        if routine.is_async and not has_await:
            # A no-Await async routine is still started eagerly as a task.
            body.append(_node(p.If(test=literal(False),
                body=[p.Expr(value=p.Yield(value=None))],orelse=[]),routine.token))
    finally:self.locals,self.globals,self.references,self.addresses,self.in_routine,self.shadows,self.in_async,self.slot_keys,self.boxed_locals=old
    body=body or [p.Pass()]
    if self.source_scopes:
        manager=call(attr(name('_C'),'routine_scope'))
        body=[p.With(items=[p.withitem(context_expr=manager,optional_vars=None)],body=body)]
    return p.FunctionDef(name=self.routines[routine.name.casefold()],args=args,
                         body=body,decorator_list=[])
