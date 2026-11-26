"""Select an address only for actual BSL reference operations."""
import ast as p
from yadinassi.execution.direct.python_direct_names import CHARS_ALIASES
from yadinassi.syntax import ast as b
from ..direct_python_ast import arguments, attr, call, literal, name


SELF_NAMES = frozenset(('thisobject', 'этотобъект'))


def reference(self,arg,known_local=False):
    while type(arg) is b.Group:
        arg=arg.expression
    path=self.import_path(arg)
    if path is not None:
        return call('_ImportedRef',call(attr(name('_C'),'import_reference'),literal(path)))
    if type(arg) is b.Name:
        key=arg.name.casefold()
        if key in self.references:
            return call('_BoundRef',name(key))
        if self.external(key):
            return call(attr(name('_C'),'external_reference'),literal(key))
        if self.implicit_self(key):
            return call('_SelfRef',name('_C'),name('_S'),literal(key))
        if key not in self.locals:
            if not self.owned and key in CHARS_ALIASES and key not in self.module_declarations:
                return call(attr(name('_C'),'character_namespace_reference'),literal(key))
            return call('_VarRef',name('_S'),literal(key))
        # Python lifts only explicitly borrowed locals into closure cells.
        getter,setter=self.address(key)
        return call('_LexicalRef',name(getter),name(setter))
    if type(arg) is b.Index:
        return call(call('_BindLocalIndexRef' if known_local else '_BindIndexRef',name('_C'),self.expr(arg.object)),self.expr(arg.index))
    if type(arg) is b.Attribute:
        return call('_LocalFieldRef' if known_local else '_FieldRef',name('_C'),self.expr(arg.object),literal(arg.name))
    return call('_Cell',self.expr(arg))


def address(self,key):
    if key not in self.addresses:
        self.addresses[key]=self.temp(),self.temp()
    return self.addresses[key]


def fragment_arguments(self):
    pairs=[]
    if self.in_routine:
        for key in sorted(self.locals):
            if key in self.references:
                value=call('_HostRef',name(key))
            else:
                getter,setter=self.address(key)
                value=call('_FragmentRef',name(getter),name(setter))
            pairs.append((literal(key),value))
    bindings=p.Dict(keys=[k for k,_ in pairs],values=[v for _,v in pairs])
    visible=literal(tuple(sorted(self.module_declarations)) if self.in_routine else None)
    return name('_C'),name('_S'),bindings,visible


def address_definitions(self):
    for key,(getter,setter) in self.addresses.items():
        yield p.FunctionDef(name=getter,args=arguments(()),
                            body=[p.Return(value=name(key))],decorator_list=[])
        yield p.FunctionDef(name=setter,args=arguments(('_Value',)),
                            body=[p.Nonlocal(names=[key]),p.Assign(targets=[name(key,True)],
                                  value=name('_Value'))],decorator_list=[])
