"""Present compiler-native BSL values using BSL rather than Python names."""
from yadinassi.application.direct_callbacks import CallbackDescription
from yadinassi.execution.codegen.direct_collections import _DIRECT_MAP_ENTRY_TYPE, _TypedMap
from yadinassi.execution.codegen.direct_structure import _DirectStructure
from yadinassi.types.values import _DIRECT_TO_STRING_ABI
from .python_direct_fixed import PlainFixedMap
from .python_direct_plain_array import PlainArray
from .python_direct_plain_map import PlainMap


def native_presentation(value):
    # Collections oracle internal.array.present describes a BSL Array,
    # not the repr of the native Python storage underneath it.
    kind = type(value)
    if kind is list or kind is PlainArray:
        return 'Массив'
    if kind is _DirectStructure:
        return 'Структура'
    if kind is PlainMap or kind is _TypedMap:
        return 'Соответствие'
    if kind is PlainFixedMap:
        return 'ФиксированноеСоответствие'
    if kind is _DIRECT_MAP_ENTRY_TYPE:
        return 'КлючИЗначение'
    if kind is CallbackDescription:
        return 'ОписаниеОповещения'
    return None


def string(value):
    native = native_presentation(value)
    return _DIRECT_TO_STRING_ABI(value) if native is None else native


def implementation(function):
    return string if function is _DIRECT_TO_STRING_ABI else function
