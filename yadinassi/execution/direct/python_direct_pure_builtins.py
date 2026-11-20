"""Bind canonical pure services only in whole units with no host effects."""
from dataclasses import dataclass
from decimal import Decimal
from types import MappingProxyType

from yadinassi.syntax import ast
from yadinassi.text import strings
from yadinassi.types.values import HostFunction, NULL, _DIRECT_COLLECTION_CLASS_ABI

_SELECTED = (strings.string_length, strings.upper, strings.lower,
             strings.trim_left, strings.trim_right, strings.trim_all,
             strings.is_blank, strings.starts_with, strings.ends_with, strings.left, strings.right)
_TWO_ARGS = (strings.starts_with, strings.ends_with, strings.left, strings.right)
_ABI = MappingProxyType({
    name.casefold(): (function, 2 if function in _TWO_ARGS else 1)
    for primary, function, english in strings.BUILTINS if function in _SELECTED
    for name in (primary, english)
})
_HOST_CALL = next(dict(entries)['__call__'] for cls, _, entries in _DIRECT_COLLECTION_CLASS_ABI
                  if cls is HostFunction)
_SCALAR_TYPES = frozenset(map(id, (str, int, bool, Decimal, type(None))))
_ALLOWED = frozenset((ast.Literal, ast.Name, ast.Group, ast.Unary, ast.Binary,
                      ast.Conditional, ast.Assign, ast.ExpressionStatement,
                      ast.If, ast.For, ast.While, ast.Break, ast.Continue))


@dataclass(frozen=True)
class PureBindings:
    names: frozenset
    services: frozenset

    def active(self, vm, context=None):
        from .python_direct_services import builtin_binding
        if (vm.allow_extensions or vm.imports or vm.database_context is not None
                or HostFunction.__call__ is not _HOST_CALL
                or HostFunction.__getattribute__ is not object.__getattribute__
                or (context is not None and (context.policy is not None or context._services is not vm.functions))):
            return False
        state=vm.variables;registry=vm.functions;snapshot=vm._builtin_functions
        # A non-str key may run Python equality while looking up an otherwise
        # innocent name. Plain dictionaries themselves are checked at admission.
        if any(type(key) is not str for mapping in (state,registry) for key in mapping):
            return False
        modules=getattr(vm,'_direct_routine_modules',{})
        return (all(value is NULL or id(type(value)) in _SCALAR_TYPES
                    for name in self.names for value in (state.get(name),))
                and all(name not in modules and builtin_binding(registry.get(name), snapshot.get(name))
                        and registry[name].function is _ABI[name][0] for name in self.services))


def analyze(nodes):
    """Unknown expressions or services invalidate the entire optimization."""
    names=set();services=set()
    for node in nodes:
        kind=type(node)
        if kind is ast.Call:
            if type(node.callee) is not ast.Name:return None
            name=node.callee.name.casefold();entry=_ABI.get(name)
            if entry is None or len(node.arguments)!=entry[1]:return None
            services.add(name)
        elif kind not in _ALLOWED:
            return None
        elif kind is ast.Name:names.add(node.name.casefold())
        elif kind is ast.For:names.add(node.name.casefold())
        elif kind is ast.Literal and node.value is not NULL and id(type(node.value)) not in _SCALAR_TYPES:
            return None
    return PureBindings(frozenset(names),frozenset(services)) if services else None


def resolve(name):
    return _ABI[name][0]
