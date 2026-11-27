"""Admit native receivers before resolving a Python method.

No name, arity, or callable reaches this boundary. Registered Python objects
and unported BSL objects cannot execute attribute hooks through this path.
"""
from yadinassi.collections.maps import BSLFixedMap, BSLMap
from yadinassi.collections.structures import BSLStructure
from yadinassi.types.values import BSLArray, BSLFixedArray
from yadinassi.execution.direct.python_direct_boxed_array_methods import ArrayMethods, FixedArrayMethods
from .direct_boundaries import BoundaryViolation
from .direct_structure import BoxedStructureMethods, _DirectStructure, _FIXED_STRUCTURE
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.execution.direct.python_direct_plain_map import BoxedMapMethods, PlainFixedMap, PlainMap


_NATIVE_RECEIVERS = (PlainArray, PlainMap, PlainFixedMap, _DirectStructure)
_NATIVE_LOOKUP = {id(kind): kind.__getattribute__ for kind in _NATIVE_RECEIVERS}


def method_receiver(value):
    kind = type(value)
    expected = _NATIVE_LOOKUP.get(id(kind))
    if expected is not None and kind.__getattribute__ is expected:
        return value
    if kind is BSLArray:
        return ArrayMethods(value)
    if kind is BSLFixedArray:
        return FixedArrayMethods(value)
    if kind is BSLMap or kind is BSLFixedMap:
        return BoxedMapMethods(value, kind)
    if kind is _FIXED_STRUCTURE or kind is BSLStructure:
        return BoxedStructureMethods(value, kind)
    raise BoundaryViolation('direct method receiver is not integrated')
