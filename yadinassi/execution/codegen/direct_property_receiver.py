"""Admit passive native storage to generated Python property access.

Unported receivers fail closed. Do not fall back to context-wide member
resolution or invoke an arbitrary Python receiver's protocol.
"""
from yadinassi.execution.direct.python_direct_plain_map import PlainFixedMap
from yadinassi.collections.value_lists import BSLValueList, BSLValueListItem
from yadinassi.collections.structures import BSLFixedStructure, BSLKeyAndValue, BSLStructure
from yadinassi.collections.value_tables import (BSLValueTable, BSLValueTableColumn,
    BSLValueTableColumnCollection, BSLValueTableRow)

from yadinassi.collections.search_directions import BSLSearchDirections
from yadinassi.collections.sort_directions import BSLSortDirections
from yadinassi.formats.json.json_processing import BSLJSONLineBreaks, BSLJSONValueTypes, BSLJSONReader, BSLJSONWriter
from yadinassi.formats.regex.regex_functions import BSLRegexGroup, BSLRegexResult
from yadinassi.formats.xml.xml_io import BSLXMLReader, XML_NODE_TYPES
from yadinassi.numeric.round_modes import ROUND_MODES
from yadinassi.text.chars import CHARS
from yadinassi.types.error_info import ERROR_CATEGORIES, _DIRECT_SNAPSHOT_ABI
from yadinassi.types.type_descriptions import BSLTypeDescription
from yadinassi.types.values import BSLFixedArray
from yadinassi.types.type_qualifiers import (
    BSLAllowedSigns, BSLAllowedLengths, BSLDateFractionsNamespace,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)

from .direct_boundaries import BoundaryViolation
from .direct_structure import _DirectStructure


_LOCAL_PROPERTY_TYPES = frozenset(map(id, (
    BSLValueTable, BSLValueTableColumnCollection, BSLValueTableColumn,
    BSLValueTableRow, BSLFixedStructure, BSLStructure, BSLValueListItem,
    BSLSortDirections, BSLJSONLineBreaks, BSLJSONValueTypes,
    BSLTypeDescription,
    BSLAllowedSigns, BSLAllowedLengths, BSLDateFractionsNamespace,
    BSLNumberQualifiers, BSLStringQualifiers, BSLDateQualifiers, BSLBinaryDataQualifiers,
)))

def property_receiver(context, value, *, write=False, key=None):
    kind = type(value)
    if value is None and not write:
        raise ValueError("Значение не является значением объектного типа")
    if kind is BSLXMLReader:
        if getattr(context, '_verify_context', True):
            context._check()
        return value
    if value is ERROR_CATEGORIES or kind is _DIRECT_SNAPSHOT_ABI[0]:
        if getattr(context, '_verify_context', True):
            context._check()
        return value
    if value is ROUND_MODES and getattr(context, "_verify_context", True) is False:
        if write:
            raise ValueError("Свойство недоступно для записи: " + key)
        return value
    if value is XML_NODE_TYPES and not write and getattr(context, '_verify_context', True) is False:
        return value
    if value is CHARS or kind is _DirectStructure or kind is BSLKeyAndValue:
        return value
    if kind is BSLRegexGroup or kind is BSLRegexResult or kind is BSLSearchDirections:
        if getattr(context, '_verify_context', True):
            context._check()
        return value
    if kind is BSLJSONReader or kind is BSLJSONWriter:
        # The classes expose only passive fields; resource operations and
        # private Python fields are never part of this property path.
        if getattr(context, '_verify_context', True):
            context._check()
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
    # Fixed arrays and maps have no dot properties; bracket entries and
    # concrete methods are separate. Do not admit any Python attribute read.
    if (kind is BSLFixedArray or kind is PlainFixedMap) and getattr(context, "_verify_context", True) is False:
        raise ValueError('Поле объекта не обнаружено')
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
