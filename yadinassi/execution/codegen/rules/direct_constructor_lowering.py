"""Class and built-in construction rules, separate from ordinary calls."""
import ast as p

from yadinassi.execution.direct.python_direct import PythonDirectUnsupported
from yadinassi.syntax import ast as b
from ..direct_python_ast import call, literal, name


_NATIVE_CONSTRUCTORS = frozenset(('array','массив','map','соответствие','structure','структура'))
_VALUE_TYPE_NAMES = frozenset(('date','дата','sortdirection','направлениесортировки','promise','обещание'))
_NONCONSTRUCTIBLE = frozenset(('formdatacollection','данныеформыколлекция',
    'formdatacollectionitem','данныеформыэлементколлекции','formtable','таблицаформы',
    'collectionindex','индексколлекции','collectionindexes','индексыколлекции'))


def lower(self, x, want_value):
    if type(x) is b.DynamicNew:
        params=literal(None) if x.parameters is None else self.expr(x.parameters)
        return call('_Construct',name('_C'),self.expr(x.type_expression),params)
    if type(x) is b.New:
        key=x.name.casefold()
        if key in ('date','дата') and not x.arguments:
            return call('_Nonconstructible',literal(x.name),literal(True))
        if key in _NONCONSTRUCTIBLE or key in _VALUE_TYPE_NAMES and not x.arguments:
            return call('_Nonconstructible',literal(x.name))
        if (self.constructor_profile is not None and key not in _NATIVE_CONSTRUCTORS
                and key not in self.constructor_profile and key not in self.ordinary_constructors
                and key not in self.tree_constructors):
            raise PythonDirectUnsupported(f'constructor {x.name}; unavailable in this execution profile')
        if key in self.bound_constructors:return self.service_call('new:'+key,x.arguments,want_value)
        if key in ('array','массив','map','соответствие'):
            if self.omissions(x.arguments):
                return call('_InvalidOmissions')
            if not x.arguments:
                return p.List(elts=[],ctx=p.Load()) if key in ('array','массив') else call('_Map')
            return call('_Array' if key in ('array','массив') else '_MapFrom',
                        *(self.expr(arg) for arg in x.arguments))
        if key in ('structure','структура'):
            if self.omissions(x.arguments):return call('_InvalidOmissions')
            return call('_Structure',*(self.expr(arg) for arg in x.arguments))
        return self.service_call('new:'+key,x.arguments,want_value)
