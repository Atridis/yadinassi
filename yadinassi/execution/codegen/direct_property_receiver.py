"""Admit passive native storage to generated Python property access.

Unported receivers fail closed. Do not fall back to context-wide member
resolution or invoke an arbitrary Python receiver's protocol.
"""
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem
from yadinassi.collections.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.collections.value_tables import (BSLValueTable, BSLValueTableColumn,
    BSLValueTableColumnCollection, BSLValueTableRow)

from yadinassi.collections.sort_directions import BSLSortDirections
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.types.type_qualifiers import (
    BSLAllowedSigns, BSLAllowedLengths, BSLDateFractionsNamespace,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)

from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure


_LOCAL_PROPERTY_TYPES = frozenset(map(id, (
    BSLValueTable, BSLValueTableColumnCollection, BSLValueTableColumn,
    BSLValueTableRow, BSLFixedStructure, BSLStructure, BSLValueListItem,
    BSLSortDirections, BSLTypeDescription,
    BSLAllowedSigns, BSLAllowedLengths, BSLDateFractionsNamespace,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)))

def property_receiver(context, value, *, write=False, key=None):
    kind = type(value)
    if kind is _DirectStructure or kind is BSLKeyAndValue:
        return value
    # These are passive local operations only. Foreign/crossing contexts
    # cannot acquire a new property capability through this admission rule.
    if (id(kind) in _LOCAL_PROPERTY_TYPES
            and getattr(context, '_verify_context', True) is False):
        return value
    if kind is BSLValueList and getattr(context, '_verify_context', True) is False:
        if write:
            if key.casefold() in ('valuetype', 'типзначения', 'availablevalues', 'доступныезначения'):
                raise ValueError('Свойство недоступно для записи: ' + key)
            raise ValueError('Поле объекта не обнаружено: ' + key)
        return _ValueListDefaultProperties(value.value_type)
    if getattr(context, '_known_method_local', False) and context.policy is None:
        from yadinassi.execution.direct import python_direct_value_tree as tree
        if tree.owns(value) and tree._ordinary_read(context):
            return tree.TreeProperties(context, value, write=write)
    from yadinassi.execution.direct.python_direct_names import OPAQUE_ENUM_IDS
    if id(value) in OPAQUE_ENUM_IDS and getattr(context, '_verify_context', True) is False:
        raise ValueError('У значения перечисления нет свойств')
    raise BoundaryViolation('direct property receiver is not integrated')

class _ValueListDefaultProperties:
    __slots__ = ('value_type',)

    def __init__(self, value_type):
        self.value_type = value_type

    def __getitem__(self, key):
        folded = key.casefold()
        if folded in ('valuetype', 'типзначения'):
            return self.value_type
        if folded in ('availablevalues', 'доступныезначения'):
            return None
        raise ValueError('Поле объекта не обнаружено: ' + key)
