"""Canonical fixed snapshots of direct arrays/structures/maps; no VM dispatch."""
from yadinassi.collections.maps import BSLMap, BSLFixedMap, _key as map_key
from yadinassi.types.values import BSLArray, BSLFixedArray, HostFunction
from yadinassi.collections.structures import BSLStructure, BSLFixedStructure, BSLKeyAndValue
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

from .python_direct_plain_map import PlainMap, PlainFixedMap
from .python_direct_plain_array import _DIRECT_PLAIN_ARRAY_TYPE
from .python_direct_numbers import public_number

FACTORIES=(BSLFixedArray,BSLFixedStructure,BSLFixedMap)
_MUTABLE_ARRAY_IDS = frozenset(map(id,(list,BSLArray,_DIRECT_PLAIN_ARRAY_TYPE)))

def construct(factory,arguments):
    from yadinassi.execution.codegen.experimental_naked_structure import _DirectStructure
    from yadinassi.execution.codegen.experimental_naked_collections import _TypedMap
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
        # Copy raw spelling/value entries, not the mapping's public payload
        # view. Keep the payloads shared just like the canonical constructor.
        result=object.__new__(BSLFixedStructure)
        result._items=dict(dict.items(arguments[0]))
        result._version=0
        return result
    if factory is BSLFixedArray and len(arguments)==1:
        source = arguments[0]
        if id(type(source)) not in _MUTABLE_ARRAY_IDS:
            raise TypeError('ФиксированныйМассив ожидает массив')
        return _freeze(source,set())
    return factory(*arguments)

def construct_source(factory, arguments):
    if factory is BSLFixedMap and len(arguments) == 1 and type(arguments[0]) is PlainMap:
        # Source session/reuse already accepts the canonical fixed snapshot.
        # Text/Undefined keys have the same identity in both map families.
        # Keep native lookup on maps with numeric/boolean aliasing or
        # other plain-only key types instead of silently retagging them.
        view = BSLMap()
        for key, value in dict.items(arguments[0]):
            kind = type(key)
            if kind is not str and key is not None:
                return construct(factory, arguments)
            view._items[(kind, key)] = key, public_number(value)
        return BSLFixedMap(view)
    return construct(factory, arguments)

def _freeze(source,active):
    identity=id(source)
    if identity in active:raise ValueError('ФиксированныйМассив с циклическими вложенными массивами пока не поддерживается')
    active.add(identity)
    try:
        # A PlainArray persisted by a preceding direct/REPL command has the
        # same backing list. Use the canonical descriptor, not user iteration.
        values = source.items if type(source) is BSLArray else list.__iter__(source)
        result = object.__new__(BSLFixedArray)
        result.items = tuple(_freeze(value,active) if id(type(value)) in _MUTABLE_ARRAY_IDS else value
                             for value in values)
        return result
    finally:active.remove(identity)

def owns(value):return type(value) in (BSLFixedArray,BSLFixedStructure,BSLFixedMap,BSLKeyAndValue,PlainFixedMap)

def get(boundary,value,name):
    if boundary._verify_context:boundary._check()
    try:return value.get_member(name)
    finally:
        if boundary._verify_context:boundary._check()

def resolve(boundary,value,name,*,require_value=False,allow_references=False):
    if boundary._verify_context:boundary._check()
    if name=='__getitem__':
        function=value.get if type(value) in (BSLFixedStructure,BSLFixedArray) else value.get_index
    elif name=='__setitem__':
        def function(*args):
            if type(value) is PlainFixedMap:
                raise ValueError('Элементы фиксированного соответствия недоступны для записи')
            raise ValueError('Фиксированная коллекция недоступна для записи')
    elif name=='__iter__':
        if type(value) not in (BSLFixedArray,BSLFixedStructure,BSLFixedMap,PlainFixedMap):raise BoundaryViolation('fixed entry is not iterable')
        function=lambda:iter(value)
    else:
        method=value.get_method(name)
        return boundary.resolve_callable(method,require_value=require_value,allow_references=allow_references)
    return boundary.resolve_callable(HostFunction(name,function),require_value=require_value,allow_references=allow_references)
