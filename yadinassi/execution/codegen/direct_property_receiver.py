"""Admit passive native storage to generated Python property access.

Unported receivers fail closed. Do not fall back to context-wide member
resolution or invoke an arbitrary Python receiver's protocol.
"""
from yadinassi.collections.structures import BSLKeyAndValue

from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure


def property_receiver(value, *, write=False):
    kind = type(value)
    if kind is _DirectStructure or (not write and kind is BSLKeyAndValue):
        return value
    raise BoundaryViolation('direct property receiver is not integrated')
