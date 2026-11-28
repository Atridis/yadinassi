"""TypeOf for the native Python representations emitted by the BSL compiler."""
from yadinassi.application.direct_callbacks import CallbackDescription
from yadinassi.collections.plain_value_list import PlainValueList, PlainValueListItem
from yadinassi.execution.codegen.direct_collections import _DIRECT_MAP_ENTRY_TYPE, _TypedMap
from yadinassi.execution.codegen.direct_structure import _DirectStructure
from yadinassi.types.type_values import _DIRECT_TYPE_OF_ABI
from yadinassi.types.value_checks import _DIRECT_VALUE_IS_FILLED_ABI
from yadinassi.types.values import BSLType
from .python_direct_fixed import PlainFixedMap
from .python_direct_plain_array import PlainArray
from .python_direct_plain_map import PlainMap, _DIRECT_FIXED_MAP_STORAGE


def type_of(value):
    # test_eval_result_uses_existing_serialization_both_directions and
    # test_type_values distinguish the emitted representations from boxed ones.
    kind = type(value)
    if kind is int:
        return BSLType.NUMBER
    if kind is list or kind is PlainArray:
        return BSLType.ARRAY
    if kind is PlainMap or kind is _TypedMap:
        return BSLType.MAP
    if kind is PlainValueList:
        return BSLType.VALUE_LIST
    if kind is PlainValueListItem:
        return BSLType.VALUE_LIST_ITEM
    if kind is PlainFixedMap:
        return BSLType.FIXED_MAP
    if kind is CallbackDescription:
        return BSLType.CALLBACK_DESCRIPTION
    if kind is _DirectStructure:
        return BSLType.STRUCTURE
    if kind is _DIRECT_MAP_ENTRY_TYPE:
        return BSLType.KEY_AND_VALUE
    return _DIRECT_TYPE_OF_ABI(value)


def value_is_filled(value):
    # Probe only the emitted representations, without truthiness or length
    # hooks on arbitrary host values. Boxed values retain the ordinary ABI.
    kind = type(value)
    if kind is int:
        return value != 0
    if kind is list or kind is PlainArray:
        return list.__len__(value) != 0
    if kind is _DirectStructure or kind is PlainMap or kind is _TypedMap:
        return dict.__len__(value) != 0
    if kind is PlainFixedMap:
        storage = _DIRECT_FIXED_MAP_STORAGE.__get__(value, PlainFixedMap)
        return dict.__len__(storage) != 0
    return _DIRECT_VALUE_IS_FILLED_ABI(value)


def implementation(function):
    if function is _DIRECT_TYPE_OF_ABI:
        return type_of
    if function is _DIRECT_VALUE_IS_FILLED_ABI:
        return value_is_filled
    return function
