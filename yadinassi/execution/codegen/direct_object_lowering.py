"""Index behavior outside the ordinary Python value lane."""
from yadinassi.syntax import ast as b
from yadinassi.types.values import NULL
from .direct_python_ast import _node, attr, call, literal, name
from .direct_reference_lowering import SELF_NAMES
import ast as p


def index(self,x):
    receiver,key=self.expr(x.object),self.expr(x.index)
    target=x.object
    while type(target) is b.Group:target=target.expression
    null_literal=type(target) is b.Literal and target.value is NULL
    if null_literal or self.meter_loops or self.source_dispatch or self.configuration_dispatch:
        return _node(call(call('_OwnedIndex',name('_C'),receiver),key),x.token)
    return _node(call('_ReadBracket',name('_C'),receiver,key),x.token)


def member_call(self, x, c, want_value):
    omitted=self.omissions(x.arguments)
    root=c.object
    while type(root) is b.Group:root=root.expression
    if (self.current_module and not self.owned and type(root) is b.Name
            and root.name.casefold() in SELF_NAMES
            and root.name.casefold() not in self.locals
            and root.name.casefold() not in self.module_declarations):
        options={'require_value':literal(want_value),'argument_count':literal(len(x.arguments))}
        if omitted:options['local_omissions']=literal(True)
        bound=call(attr(name('_C'),'resolve_public_module_call'),self.expr(root),literal(c.name),**options)
        return self.bound_call(bound,x.arguments,omitted,references=True)
    qualifier=root
    while type(qualifier) in (b.Group,b.Attribute):
        qualifier=qualifier.expression if type(qualifier) is b.Group else qualifier.object
    if self.source_dispatch and type(qualifier) is b.Name and self.external(qualifier.name.casefold()):
        bound=call('_Member',name('_C'),self.expr(c.object),literal(c.name),
                   literal(len(x.arguments)),literal(want_value),literal(omitted),source_dispatch=literal(True))
        return self.bound_call(bound,x.arguments,omitted,references=True,crossing=True,shapes=True)
    if omitted:
        target=root
        while type(target) in (b.Group,b.Attribute):
            target=target.expression if type(target) is b.Group else target.object
        if type(target) is not b.Name:return call('_InvalidOmissions')
    binding=[] if not omitted else [literal(omitted)]
    receiver=self.expr(c.object)
    property_output=not omitted and len(x.arguments)==2 and c.name.casefold() in ('property','свойство')
    if property_output:
        slot=self.temp()
        receiver=p.NamedExpr(target=name(slot,True),value=receiver)
    bound=call('_Member',name('_C'),receiver,literal(c.name),
               literal(len(x.arguments)),literal(want_value),*binding,
               **({'source_dispatch':literal(True)} if self.source_dispatch else
                  {'configuration_dispatch':literal(True)} if self.configuration_dispatch else {}))
    if self.source_dispatch and not omitted and not property_output:
        return self.bound_call(bound,x.arguments,omitted,references=True,crossing=True,shapes=True)
    if property_output:
        native=call('_OwnsPropertyOutput',name(slot))
        return call(bound,self.expr(x.arguments[0]),self.actual_address(x.arguments[1],native))
    return call(bound,*(literal(None) if i in omitted else self.expr(arg)
                        for i,arg in enumerate(x.arguments)))
