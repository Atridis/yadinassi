"""Documented filled-value checks for the supported scalar/collection and measured service subset."""

from decimal import Decimal

from .dates import BSLDate

from .maps import BSLFixedMap, BSLMap
from .strings import is_blank
from .structures import BSLFixedStructure, BSLStructure
from .values import BSLArray, BSLFixedArray, BSLType, NULL
from .round_modes import BSLRoundMode, BSLRoundModes, ROUND_MODES
from .type_descriptions import BSLTypeDescription
from .type_qualifiers import (BSLNumberQualifiers, BSLStringQualifiers,
                              BSLDateQualifiers, BSLBinaryDataQualifiers,
                              BSLAllowedSign, BSLAllowedLength, BSLDateFractions)
from .value_tables import BSLValueTable


def _number_qualifier_filled(value):
    # None means unmeasured, not an empty value. Only native-observed states.
    if (type(value) is not BSLNumberQualifiers
            or type(value.digits) is not Decimal
            or type(value.fraction_digits) is not Decimal
            or not value.digits.is_finite() or not value.fraction_digits.is_finite()
            or value.allowed_sign is not BSLAllowedSign.ANY):
        return None
    if value.digits == 0 and value.fraction_digits == 0:
        return False
    if value.digits == 10 and value.fraction_digits == 2:
        return True
    return None


def _string_qualifier_filled(value):
    if (type(value) is not BSLStringQualifiers or type(value.length) is not Decimal
            or not value.length.is_finite()):
        return None
    if value.length == 0 and value.allowed_length is BSLAllowedLength.VARIABLE:
        return False
    if value.length == 4 and value.allowed_length is BSLAllowedLength.FIXED:
        return True
    return None


def _plain_description_filled(value):
    # No inference for composite types or qualified descriptions. Qualifiers
    # and the type tuple are checked explicitly, never compared as host objects.
    date, binary = value.date_qualifiers, value.binary_data_qualifiers
    if (_number_qualifier_filled(value.number_qualifiers) is not False
            or _string_qualifier_filled(value.string_qualifiers) is not False
            or type(date) is not BSLDateQualifiers
            or date.date_fractions is not BSLDateFractions.DATE_TIME
            or type(binary) is not BSLBinaryDataQualifiers
            or type(binary.length) is not Decimal or not binary.length.is_finite()
            or binary.length != 0 or binary.allowed_length is not BSLAllowedLength.VARIABLE
            or type(value.types) is not tuple):
        return None
    if len(value.types) == 0:
        return False
    if len(value.types) == 1 and (value.types[0] is BSLType.NUMBER
                                or value.types[0] is BSLType.STRING):
        return True
    return None


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
    if kind is BSLValueTable:
        return len(value.rows) != 0
    if kind is BSLType and (value is BSLType.NUMBER or value is BSLType.STRING):
        return True
    if kind is BSLRoundMode and (value is BSLRoundMode.ROUND15_AS10
                                 or value is BSLRoundMode.ROUND15_AS20):
        return True  # Only the two independently measured enum identities.
    if kind is BSLRoundModes and value is ROUND_MODES:
        return True  # Exact known namespace, not iteration or host truthiness.
    observed = None
    if kind is BSLNumberQualifiers:
        observed = _number_qualifier_filled(value)
    elif kind is BSLStringQualifiers:
        observed = _string_qualifier_filled(value)
    elif kind is BSLTypeDescription:
        observed = _plain_description_filled(value)
    if observed is not None:
        return observed
    # Other service values/configurations remain unmeasured. This deliberately
    # does not claim complete descriptor/qualifier/enum support.
    raise TypeError("ЗначениеЗаполнено для этого типа пока не поддерживается в Yadinassi")
