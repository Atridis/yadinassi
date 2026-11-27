"""Admit passive native storage to generated Python property access.

Unported receivers fail closed. Do not fall back to context-wide member
resolution or invoke an arbitrary Python receiver's protocol.
"""
from yadinassi.collections.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.collections.value_tables import (BSLValueTable, BSLValueTableColumn,
    BSLValueTableColumnCollection, BSLValueTableRow)

from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure


_LOCAL_PROPERTY_TYPES = frozenset(map(id, (
    BSLValueTable, BSLValueTableColumnCollection, BSLValueTableColumn,
    BSLValueTableRow, BSLFixedStructure, BSLStructure,
)))

def property_receiver(context, value, *, write=False):
    kind = type(value)
    if kind is _DirectStructure or kind is BSLKeyAndValue:
        return value
    # These are passive local operations only. Foreign/crossing contexts
    # cannot acquire a new property capability through this admission rule.
    if (id(kind) in _LOCAL_PROPERTY_TYPES
            and getattr(context, '_verify_context', True) is False):
        return value
    if getattr(context, '_known_method_local', False) and context.policy is None:
        from yadinassi.execution.direct import python_direct_value_tree as tree
        if tree.owns(value) and tree._ordinary_read(context):
            return tree.TreeProperties(context, value, write=write)
    raise BoundaryViolation('direct property receiver is not integrated')
