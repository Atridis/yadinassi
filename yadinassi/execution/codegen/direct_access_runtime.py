"""Runtime differences in BSL member, index, and iteration protocols."""
from decimal import Decimal

from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.execution.direct.python_direct_plain_map import PlainFixedMap, PlainMap
from yadinassi.temporal.dates import BSLDate
from yadinassi.types.array_index import array_offset
from yadinassi.types.values import BSLObject
from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure


_TYPE_MRO = vars(type)["__mro__"]
_TYPE_DICT = vars(type)["__dict__"]
# Dates use the existing member policy even though they are not BSLObjects.
_BRACKET_RECEIVER_TYPES = (BSLObject, BSLDate)


def owned_index(context,receiver):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        return lambda key: receiver[array_offset(receiver,key)]
    if kind is PlainMap or kind is _DirectStructure:
        return receiver.__getitem__
    return context.resolve_member(receiver,'__getitem__')


def read_bracket(context, receiver, key):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        return receiver[array_offset(receiver,key)]
    if kind is dict:
        return receiver.get(key)
    if kind is not BSLMap and kind is not BSLFixedMap and issubclass(kind,_BRACKET_RECEIVER_TYPES):
        return context.resolve_member(receiver,'__getitem__')(key)
    return receiver[key]


def write_bracket(context, receiver, key, value):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        key=array_offset(receiver,key)
    elif kind is not BSLMap and kind is not BSLFixedMap and issubclass(kind,_BRACKET_RECEIVER_TYPES):
        context.resolve_member(receiver,'__setitem__')(key,value)
        return
    receiver[key]=value


def owned_set_index(context,value,receiver,key):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        receiver[array_offset(receiver,key)] = value
    elif kind is PlainMap or kind is _DirectStructure:
        receiver[key] = value
    else:
        context.resolve_member(receiver,'__setitem__')(key,value)


def owned_iterable(context, iterable):
    kind=type(iterable)
    if kind is list or kind is PlainArray or kind is _DirectStructure:
        return iter(iterable)
    if kind is PlainMap:
        return iterable.bsl_entries()
    return context.resolve_member(iterable,'__iter__')()


def bsl_iterable(context, iterable):
    # PlainMap implements the Python mapping protocol for host callers. Only
    # BSL's loop enumerates its logical pairs instead of its keys.
    kind=type(iterable)
    if kind is list or kind is _DirectStructure:
        return iterable
    if kind is PlainArray:
        return list.__iter__(iterable)
    if kind is PlainMap:
        return iterable.bsl_entries()
    if kind is PlainFixedMap:
        return PlainFixedMap.__iter__(iterable)
    if issubclass(kind,BSLObject):
        return context.resolve_member(iterable,'__iter__')()
    # Exact Python values retain their existing data/error behavior. A
    # foreign object must not run __iter__ or the sequence-protocol fallback.
    if any(kind is native for native in (tuple,dict,str,bytes,bytearray,range,
                                         set,frozenset,type(None),bool,int,Decimal,float)):
        return iterable
    # Inspect slots without invoking user metaclass attributes. For passive
    # values, preserve Python's catchable non-iterable error.
    for cls in _TYPE_MRO.__get__(kind):
        namespace = _TYPE_DICT.__get__(cls)
        if '__iter__' in namespace or '__getitem__' in namespace:
            raise BoundaryViolation('For Each requires an admitted BSL iterator')
    return iterable


def metered(context, iterable):
    iterator=iter(owned_iterable(context,iterable))
    while True:
        context.checkpoint()
        try:
            value=next(iterator)
        except StopIteration:
            return
        yield value


def owns_property_output(receiver):
    kind = type(receiver)
    return kind is _DirectStructure or kind is BSLStructure or kind is BSLFixedStructure
