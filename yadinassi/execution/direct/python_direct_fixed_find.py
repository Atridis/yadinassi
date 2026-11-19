"""FixedArray.Find retains identity of direct mutable collection payloads."""
from decimal import Decimal
from types import MethodType
from yadinassi.types.values import HostFunction, _DIRECT_FIXED_ARRAY_TYPE as _FIXED, _DIRECT_FIXED_FIND_ABI
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation
from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap

_FIND,_ABI=_DIRECT_FIXED_FIND_ABI


def owns(value,name):
    return type(value) is _FIXED and type(name) is str and name.casefold() in ('find','найти')


def _check(boundary,value):
    boundary._check()
    for cls,mro,entries in _ABI:
        actual=cls.__mro__;current=vars(cls)
        if (len(actual)!=len(mro) or any(a is not b for a,b in zip(actual,mro))
                or len(current)!=len(entries) or any(current.get(k) is not v for k,v in entries)):
            raise BoundaryViolation('fixed Find receiver ABI changed')
    fields=vars(value)
    if (any(type(key) is not str for key in fields) or set(fields)!={'items'}
            or type(fields['items']) is not tuple):
        raise BoundaryViolation('fixed Find storage changed')
    return fields['items']


def captured(boundary,function,*,require_value=False,allow_references=False,_operation='call_value'):
    if type(function) is not HostFunction or type(function.function) is not MethodType:return None
    callback=function.function;receiver=callback.__self__
    if type(receiver) is not _FIXED or callback.__func__ is not _FIND:return None
    def check():
        items=_check(boundary,receiver)
        if (function.function is not callback or function.returns_value is not True
                or type(function.reference_parameters) is not frozenset or function.reference_parameters
                or type(function.name) is not str):
            raise BoundaryViolation('fixed Find captured method changed')
        return items
    check()
    def invoke(*args):
        check();boundary._before(_operation,function.name.casefold());items=check()
        if len(args)!=1:raise TypeError('Find requires one argument')
        needle=args[0]
        try:
            if type(needle) is _DirectStructure or type(needle) is _TypedMap:
                for index,item in enumerate(items):
                    if item is needle:return Decimal(index)
                return None
            return _FIND(receiver,needle)
        finally:check()
    if allow_references:invoke.requires_reference=lambda index:False
    return invoke


def resolve(boundary,value,name):
    _check(boundary,value)
    return captured(boundary,HostFunction(name,_FIND.__get__(value,_FIXED)),_operation='call_member')
