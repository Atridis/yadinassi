"""FixedArray.Find retains identity of direct mutable collection payloads."""
from types import MethodType
from yadinassi.types.values import HostFunction, _DIRECT_FIXED_ARRAY_TYPE as _FIXED, _DIRECT_FIXED_FIND_ABI
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.execution.codegen.direct_scalar_semantics import (
    _DATE_TYPE, _FIND_DIRECT_COLLECTION_IDS, find_by_identity, find_date,
)

from .python_direct_plain_map import _DIRECT_PLAIN_MAP_FIND_TYPES

_FIND,_ABI=_DIRECT_FIXED_FIND_ABI
_IDENTITY_NEEDLE_IDS = _FIND_DIRECT_COLLECTION_IDS | frozenset(map(id,_DIRECT_PLAIN_MAP_FIND_TYPES))


def owns(value,name):
    return type(value) is _FIXED and type(name) is str and name.casefold() in ('find','найти')


def _check(boundary,value):
    if boundary._verify_context:boundary._check()
    for cls,mro,entries in _ABI:
        actual=cls.__mro__;current=vars(cls)
        if ((actual is not mro and
                (len(actual)!=len(mro) or any(a is not b for a,b in zip(actual,mro))))
                or len(current)!=len(entries) or any(current.get(k) is not v for k,v in entries)):
            raise BoundaryViolation('fixed Find receiver ABI changed')
    fields=vars(value)
    if len(fields)!=1:
        raise BoundaryViolation('fixed Find storage changed')
    key,=fields
    if type(key) is not str or key!='items':
        raise BoundaryViolation('fixed Find storage changed')
    items=fields[key]
    if type(items) is not tuple:
        raise BoundaryViolation('fixed Find storage changed')
    return items


def _bind(boundary,receiver,operation,name,*,function=None,callback=None,allow_references=False):
    def check():
        items=_check(boundary,receiver)
        if function is not None and (
                function.function is not callback or function.returns_value is not True
                or type(function.reference_parameters) is not frozenset or function.reference_parameters
                or type(function.name) is not str):
            raise BoundaryViolation('fixed Find captured method changed')
        return items

    check()
    def invoke(*args):
        check()
        spelling=name if function is None else function.name
        boundary._before(operation,spelling.casefold())
        items=check()
        if len(args)!=1:raise TypeError('Find requires one argument')
        needle=args[0]
        try:
            kind=type(needle)
            if kind is _DATE_TYPE:
                return find_date(items,needle)
            if id(kind) in _IDENTITY_NEEDLE_IDS:
                return find_by_identity(items,needle)
            return _FIND(receiver,needle)
        finally:check()
    if allow_references:invoke.requires_reference=lambda index:False
    return invoke


def captured(boundary,function,*,require_value=False,allow_references=False):
    if type(function) is not HostFunction or type(function.function) is not MethodType:return None
    callback=function.function;receiver=callback.__self__
    if type(receiver) is not _FIXED or callback.__func__ is not _FIND:return None
    return _bind(boundary,receiver,'call_value',None,function=function,callback=callback,
                 allow_references=allow_references)


def resolve(boundary,value,name):
    # A named receiver does not need a transient HostFunction capture. Bind
    # the canonical operation once; only real wrappers need metadata checks.
    if type(value) is not _FIXED:return None
    if type(name) is not str:raise TypeError('Find requires a method name')
    return _bind(boundary,value,'call_member',name)
