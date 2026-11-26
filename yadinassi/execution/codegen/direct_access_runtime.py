"""Runtime differences in BSL member, index, and iteration protocols."""
from decimal import Decimal
from functools import partial

from yadinassi.collections.maps import BSLMap, BSLFixedMap
from yadinassi.collections.structures import BSLKeyAndValue, BSLStructure, BSLFixedStructure
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.execution.direct.python_direct_plain_map import PlainMap
from yadinassi.types.array_index import array_offset
from yadinassi.types.values import BSLObject, HostFunction
from .direct_boundaries import BoundaryViolation
from .direct_collections import _host_omission_error
from .direct_resources import bounded_insert
from .direct_scalar_semantics import typed_find
from .direct_structure import _DirectStructure


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
    if kind is not BSLMap and kind is not BSLFixedMap and issubclass(kind,BSLObject):
        return context.resolve_member(receiver,'__getitem__')(key)
    return receiver[key]


def write_bracket(context, receiver, key, value):
    kind=type(receiver)
    if kind is list or kind is PlainArray:
        key=array_offset(receiver,key)
    elif kind is not BSLMap and kind is not BSLFixedMap and issubclass(kind,BSLObject):
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
    if kind is PlainMap:
        return iterable.bsl_entries()
    if issubclass(kind,BSLObject):
        return context.resolve_member(iterable,'__iter__')()
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


ARRAY_ALIASES={'количество':'count','вграница':'ubound','добавить':'add','очистить':'clear',
          'получить':'get','установить':'set','вставить':'insert','удалить':'delete','найти':'find'}


def get_field(context, receiver, key):
    kind = type(receiver)
    if kind is list or kind is PlainArray:
        operation = ARRAY_ALIASES.get(key.casefold(), key.casefold())
        if operation in _ARRAY_ARITY:
            from yadinassi.execution.direct.python_direct_captured_values import register

            def invoke(*args):
                return array_method(receiver, key, len(args), False, ())(*args)

            return register(HostFunction(key, invoke, returns_value=operation not in _ARRAY_PROCEDURES))
    if kind is _DirectStructure:
        return receiver[key]
    if kind is PlainMap:
        raise ValueError('Свойство соответствия не найдено: '+key)
    if kind is BSLKeyAndValue:
        return receiver.get_member(key)
    return context.get_member(receiver,key)


def owns_property_output(receiver):
    kind=type(receiver)
    return kind is _DirectStructure or kind is BSLStructure or kind is BSLFixedStructure


def set_field(context, receiver, key):
    kind=type(receiver)
    if kind is _DirectStructure:
        return lambda value: receiver.__setitem__(key,value)
    if kind is PlainMap:
        raise ValueError('Свойство соответствия недоступно для записи: '+key)
    return context.resolve_set_member(receiver,key)


_ARRAY_ARITY = {'ubound':(0,0),'count':(0,0),'add':(0,1),'clear':(0,0),
                'get':(1,1),'set':(2,2),'insert':(1,2),'delete':(1,1),'find':(1,1)}


_ARRAY_PROCEDURES = frozenset(('add','clear','set','insert','delete'))


def array_get(receiver,index):
    return receiver[array_offset(receiver,index,method=True)]


def array_set(receiver,index,value):
    receiver[array_offset(receiver,index,method=True)] = value


def array_add(receiver,value=None):
    receiver.append(value)


def array_ubound(receiver):
    return len(receiver)-1


def array_delete(receiver,index):
    if type(index) is Decimal and (not index.is_finite() or index!=index.to_integral_value()):
        raise ValueError('Ожидается целое число')
    del receiver[array_offset(receiver,index)]


def array_find(receiver,value):
    if type(value) in (int,Decimal):
        for index,item in enumerate(receiver):
            if type(item) in (int,Decimal) and item==value:
                return index
        return None
    return typed_find(receiver,value)


_ARRAY_CALLS = {'ubound':array_ubound,'add':array_add,'get':array_get,'set':array_set,
                'insert':bounded_insert,'delete':array_delete,'find':array_find}


_MAP_ALIASES = {'вставить':'insert','удалить':'delete','очистить':'clear',
                'получить':'get','количество':'count'}


_MAP_ARITY = {'insert':(1,2),'delete':(1,1),'clear':(0,0),'get':(1,1),'count':(0,0)}


def reject_runtime_arity(key,count,arity):
    # A resolved collection method evaluates ordinary actuals before reporting
    # invalid arity, and drops temporaries before entering the BSL handler.
    expected=str(arity[0]) if arity[0]==arity[1] else f'{arity[0]}–{arity[1]}'
    def wrong_arity(*actuals):
        del actuals
        raise TypeError(f'{key} ожидает {expected} аргументов, получено {count}')
    return wrong_arity


def array_method(receiver,key,count,want_value,omitted):
    folded=key.casefold()
    operation=ARRAY_ALIASES.get(folded,folded)
    arity=_ARRAY_ARITY.get(operation)
    if arity is None:
        raise ValueError('Метод или свойство не найдено: '+key)
    if omitted:
        raise TypeError('Неверное количество аргументов: '+key)
    if not arity[0]<=count<=arity[1]:
        return reject_runtime_arity(key,count,arity)
    if want_value and operation in _ARRAY_PROCEDURES:
        raise TypeError('Процедура не возвращает значение: '+key)
    if operation=='count':return receiver.__len__
    if operation=='add' and count:return receiver.append
    if operation=='clear':return receiver.clear
    return partial(_ARRAY_CALLS[operation],receiver)


def member(context, receiver, key, count, want_value, omitted=(), source_dispatch=False,configuration_dispatch=False):
    kind=type(receiver)
    if kind is list or kind is PlainArray:return array_method(receiver,key,count,want_value,omitted)
    folded=key.casefold()
    if not omitted and kind is _DirectStructure:
        # Bind known methods even with the wrong count. Let Python report
        # their arity after evaluating actuals, not the unrelated DB resolver.
        if folded in ('property','свойство'):return receiver.property
        if folded in ('insert','вставить'):
            if want_value and count in (1,2):raise TypeError('Процедура не возвращает значение: '+key)
            return receiver.insert
        if folded in ('delete','удалить'):
            if want_value and count==1:raise TypeError('Процедура не возвращает значение: '+key)
            return receiver.__delitem__
        if folded in ('clear','очистить'):
            if want_value and not count:raise TypeError('Процедура не возвращает значение: '+key)
            return receiver.clear
        if folded in ('count','количество'):return receiver.__len__
        raise ValueError('Метод структуры не найден: '+key)
    if kind is PlainMap:
        operation=_MAP_ALIASES.get(folded,folded)
        arity=_MAP_ARITY.get(operation)
        if arity is None:
            raise ValueError('Метод соответствия не найден: '+key)
        if omitted:
            raise TypeError('Неверное количество аргументов: '+key)
        if not arity[0]<=count<=arity[1]:
            return reject_runtime_arity(key,count,arity)
        if operation=='get':return receiver.get
        if operation=='count':return receiver.__len__
        if want_value:raise TypeError('Процедура не возвращает значение: '+key)
        if operation=='insert':
            if count==2:return receiver.__setitem__
            return lambda item:receiver.__setitem__(item,None)
        if operation=='delete':return receiver.__delitem__
        return receiver.clear
    if (omitted and not (configuration_dispatch or source_dispatch)
            and folded in ('openfile','открытьфайл')):
        return context.resolve_optional_open_file(receiver,key,require_value=want_value,
                                                  omitted=omitted,argument_count=count)
    if configuration_dispatch:
        return context.resolve_configuration_member_call(receiver,key,require_value=want_value,omitted=omitted,argument_count=count)
    if source_dispatch:
        return context.resolve_source_member(receiver,key,require_value=want_value,argument_count=count,allow_references=True)
    return context.resolve_member_call(receiver,key,require_value=want_value,omitted=omitted)
