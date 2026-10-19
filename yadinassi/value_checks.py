"""Documented filled-value checks for the supported scalar/collection subset."""

from decimal import Decimal

from .dates import BSLDate

from .maps import BSLFixedMap, BSLMap
from .strings import is_blank
from .structures import BSLFixedStructure, BSLStructure
from .values import BSLArray, BSLFixedArray, NULL


def value_is_filled(value: object) -> bool:
    # Exact types avoid invoking arbitrary extension truth/length/iteration hooks.
    kind = type(value)
    if value is None or value is NULL:
        return False
    if kind is bool:
        return True  # False is filled too; this is not a Boolean conversion.
    if kind is Decimal:
        if not value.is_finite():
            raise ValueError("Ожидается конечное число")
        return not value.is_zero()
    if kind is BSLDate:
        return value.require_known().ticks != 0
    if kind is str:
        return not is_blank(value)
    if kind is BSLArray or kind is BSLFixedArray:
        return len(value.items) != 0
    if (kind is BSLStructure or kind is BSLFixedStructure
            or kind is BSLMap or kind is BSLFixedMap):
        return len(value._items) != 0
    # Defaults for type descriptors, system enums and other objects have not
    # been established. Do not invent native behavior or use Python truthiness.
    raise TypeError("ЗначениеЗаполнено для этого типа пока не поддерживается в Yadinassi")
