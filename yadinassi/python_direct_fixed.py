"""Canonical fixed snapshots of direct arrays/structures/maps; no VM dispatch."""
from .maps import BSLMap, BSLFixedMap, _key as map_key
from .values import BSLArray, BSLFixedArray, HostFunction
from .structures import BSLStructure, BSLFixedStructure, BSLKeyAndValue
from .experimental_naked_boundaries import BoundaryViolation

from .python_direct_plain_map import PlainMap, PlainFixedMap

FACTORIES=(BSLFixedArray,BSLFixedStructure,BSLFixedMap)

def construct(factory,arguments):
    from .experimental_naked_structure import _DirectStructure
    from .experimental_naked_collections import _TypedMap
    if factory is BSLFixedMap and len(arguments)==1:
        source=arguments[0]
        if type(source) is PlainMap:return PlainFixedMap(source)
        if type(source) is _TypedMap:
            view=BSLMap()
            for key,value in dict.values(source):
                token=map_key(key)
                if token in view._items:
                    raise ValueError("FixedMap: distinct direct keys collide under canonical key semantics")
                view._items[token]=(key,value)
            return BSLFixedMap(view)
        if type(source) is not BSLMap:raise TypeError("ФиксированноеСоответствие ожидает соответствие")
    if factory is BSLFixedStructure and len(arguments)==1 and type(arguments[0]) is _DirectStructure:
        # The canonical constructor makes the shallow snapshot. This temporary
        # view shares storage only until that synchronous constructor returns.
        source=object.__new__(BSLStructure)
        source._items=arguments[0]
        source._version=0
        return BSLFixedStructure(source)
    if factory is BSLFixedArray and len(arguments)==1 and type(arguments[0]) not in (list,BSLArray):
        raise TypeError('ФиксированныйМассив ожидает массив')
    if factory is BSLFixedArray and len(arguments)==1 and type(arguments[0]) in (list,BSLArray):
        return _freeze(arguments[0],set())
    return factory(*arguments)

def _freeze(source,active):
    identity=id(source)
    if identity in active:raise ValueError('ФиксированныйМассив с циклическими вложенными массивами пока не поддерживается')
    active.add(identity)
    try:
        values=source if type(source) is list else source.items
        result=object.__new__(BSLFixedArray)
        result.items=tuple(_freeze(value,active) if type(value) in (list,BSLArray) else value for value in values)
        return result
    finally:active.remove(identity)

def owns(value):return type(value) in (BSLFixedArray,BSLFixedStructure,BSLFixedMap,BSLKeyAndValue,PlainFixedMap)

def get(boundary,value,name):
    boundary._check()
    try:return value.get_member(name)
    finally:boundary._check()

def resolve(boundary,value,name,*,require_value=False,allow_references=False):
    boundary._check()
    if name=='__getitem__':
        function=value.get if type(value) in (BSLFixedStructure,BSLFixedArray) else value.get_index
    elif name=='__setitem__':
        def function(*args):raise ValueError('Фиксированная коллекция недоступна для записи')
    elif name=='__iter__':
        if type(value) not in (BSLFixedArray,BSLFixedStructure,BSLFixedMap,PlainFixedMap):raise BoundaryViolation('fixed entry is not iterable')
        function=lambda:iter(value)
    else:
        method=value.get_method(name)
        return boundary.resolve_callable(method,require_value=require_value,allow_references=allow_references)
    return boundary.resolve_callable(HostFunction(name,function),require_value=require_value,allow_references=allow_references)
