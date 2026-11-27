"""Admit native receivers before resolving a Python method.

No name, arity, or callable reaches this boundary. Registered Python objects
and unported BSL objects cannot execute attribute hooks through this path.
"""
from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure
from yadinassi.execution.direct.python_direct_plain_array import PlainArray
from yadinassi.execution.direct.python_direct_plain_map import PlainMap


_NATIVE_RECEIVERS = (PlainArray, PlainMap, _DirectStructure)
_NATIVE_LOOKUP = {id(kind): kind.__getattribute__ for kind in _NATIVE_RECEIVERS}


def method_receiver(value):
    kind = type(value)
    expected = _NATIVE_LOOKUP.get(id(kind))
    if expected is not None and kind.__getattribute__ is expected:
        return value
    raise BoundaryViolation('direct method receiver is not integrated')
