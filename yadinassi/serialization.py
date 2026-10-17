"""Internal serialization, extended only from observed native payloads.

This is not JSON, a stable interchange format, or numeric presentation. Each
implemented runtime type must have an explicit policy below. Pending types are
not claimed to be refused by 1C: their payload/eligibility still needs a native
probe. New codecs belong here rather than in String() or the value classes.
"""

from decimal import Decimal
import re

from .type_values import type_of
from .values import BSLType


_MAX_NUMBER_DIGITS = 4096  # Yadinassi resource budget, not a native limit.
_CANONICAL_NUMBER = re.compile(r'\{"N",(-?(?:0|[1-9][0-9]*)(?:\.[0-9]*[1-9])?)\}')


def _number(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("ЗначениеВСтрокуВнутр: ожидается конечное число")
    if value.is_zero():
        return '{"N",0}'
    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
        exponent += 1
    digits = digits[:end]
    # Check before fixed-point expansion, including hostile host-supplied
    # exponents. Tuple construction/formatting never round in Decimal context.
    if max(len(digits) + max(exponent, 0), -exponent) > _MAX_NUMBER_DIGITS:
        raise ValueError("ЗначениеВСтрокуВнутр: превышен предел ресурсов Yadinassi (4096 десятичных разрядов)")
    return '{"N",' + format(Decimal((sign, digits, exponent)), "f") + '}'


_SERIALIZERS = {BSLType.NUMBER: _number}
_AWAITING_NATIVE = frozenset({
    BSLType.UNDEFINED, BSLType.BOOLEAN, BSLType.STRING,
    BSLType.ARRAY, BSLType.FIXED_ARRAY,
    BSLType.STRUCTURE, BSLType.FIXED_STRUCTURE,
    BSLType.MAP, BSLType.FIXED_MAP,
    BSLType.TYPE, BSLType.KEY_AND_VALUE,
})


def value_to_string_internal(value: object) -> str:
    """Serialize an explicitly supported BSL value without host reflection."""
    try:
        value_type = type_of(value)
    except TypeError:
        raise TypeError("ЗначениеВСтрокуВнутр: значение не относится к поддерживаемым типам BSL") from None
    serializer = _SERIALIZERS.get(value_type)
    if serializer is not None:
        return serializer(value)
    if value_type in _AWAITING_NATIVE:
        raise ValueError(
            f"ЗначениеВСтрокуВнутр: тип {value_type} пока не поддерживается в Yadinassi; "
            "ожидается проверка на 1С")
    # A newly added runtime type must not silently fall back to str/repr/JSON.
    raise ValueError("ЗначениеВСтрокуВнутр: для типа не задана политика сериализации Yadinassi")


def value_from_string_internal(text: object) -> object:
    """Read only the bounded numeric form we emit; never evaluate input text.

    Native acceptance of alternate spelling, whitespace, malformed payloads and
    other tags remains unverified. Rejection here is a Yadinassi limitation,
    not an attempt to reproduce a native diagnostic or permissive grammar.
    """
    if type(text) is not str:
        raise TypeError("ЗначениеИзСтрокиВнутр: ожидается строка")
    # Largest emitted number: minus, leading 0., 4096 fraction digits, wrapper.
    # Bound input before regex matching or allocating a Decimal coefficient.
    if len(text) > _MAX_NUMBER_DIGITS + 9:
        raise ValueError("ЗначениеИзСтрокиВнутр: превышен предел ресурсов Yadinassi (4096 десятичных разрядов)")
    match = _CANONICAL_NUMBER.fullmatch(text)
    if match is not None:
        value = Decimal(match[1])
        try:
            canonical = _number(value)
        except ValueError:
            # The grammar guarantees a finite number; only the resource budget
            # can fail here. Keep the diagnostic attached to the read operation.
            raise ValueError("ЗначениеИзСтрокиВнутр: превышен предел ресурсов Yadinassi (4096 десятичных разрядов)") from None
        if canonical == text:
            return value
    raise ValueError("ЗначениеИзСтрокиВнутр: формат пока не поддерживается в Yadinassi; ожидается проверка на 1С")
