"""Admit passive native storage to generated Python property access.

Unported receivers fail closed. Do not fall back to context-wide member
resolution or invoke an arbitrary Python receiver's protocol.
"""
from yadinassi.collections.structures import BSLFixedStructure, BSLKeyAndValue
from yadinassi.collections.value_tables import (BSLValueTable, BSLValueTableColumn,
    BSLValueTableColumnCollection, BSLValueTableRow)

from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure


_TABLE_WRITES = frozenset(map(id, (BSLValueTableColumn, BSLValueTableRow)))
_TABLE_READS = _TABLE_WRITES | frozenset(map(id, (
    BSLValueTable, BSLValueTableColumnCollection, BSLFixedStructure,
)))


def property_receiver(context, value, *, write=False):
    kind = type(value)
    if kind is _DirectStructure or (not write and kind is BSLKeyAndValue):
        return value
    # These are passive local operations only. Foreign/crossing contexts
    # cannot acquire a new property capability through this admission rule.
    if (id(kind) in (_TABLE_WRITES if write else _TABLE_READS)
            and getattr(context, '_verify_context', True) is False):
        return value
    raise BoundaryViolation('direct property receiver is not integrated')
