"""Documented unsigned 32-bit logical operations (1C 8.3.11 and later).

Only the documented Number/Boolean argument types are accepted. Coercion and
native error wording are intentionally not inferred from unrelated builtins.
"""

from decimal import Decimal

_MAX = 2**32 - 1


def _integer(value: object, maximum: int = _MAX) -> int:
    # Check the bounded Decimal before int(): gigantic exponents must not allocate
    # gigantic integers. Neither comparison nor int conversion rounds in context.
    if type(value) is not Decimal or not value.is_finite():
        raise TypeError("Побитовая операция: ожидается конечное число")
    if value < 0 or value > maximum:
        raise ValueError(f"Побитовая операция: число должно быть от 0 до {maximum}")
    result = int(value)
    if value != result:
        raise ValueError("Побитовая операция: ожидается целое число")
    return result


def bitwise_and(first: object, second: object) -> Decimal:
    return Decimal(_integer(first) & _integer(second))


def bitwise_or(first: object, second: object) -> Decimal:
    return Decimal(_integer(first) | _integer(second))


def bitwise_xor(first: object, second: object) -> Decimal:
    return Decimal(_integer(first) ^ _integer(second))


def bitwise_not(value: object) -> Decimal:
    return Decimal(_MAX ^ _integer(value))


def bitwise_and_not(first: object, second: object) -> Decimal:
    return Decimal(_integer(first) & (_MAX ^ _integer(second)))


def check_bit(value: object, position: object) -> bool:
    return bool(_integer(value) & (1 << _integer(position, 31)))


def check_by_bit_mask(value: object, mask: object) -> bool:
    number, mask = _integer(value), _integer(mask)
    return number & mask == mask


def set_bit(value: object, position: object, enabled: object) -> Decimal:
    number, bit = _integer(value), 1 << _integer(position, 31)
    if type(enabled) is not bool:
        raise TypeError("УстановитьБит: значение бита должно иметь тип Булево")
    return Decimal(number | bit if enabled else number & (_MAX ^ bit))


BUILTINS = (
    ("ПобитовоеИ", bitwise_and, "BitwiseAnd"),
    ("ПобитовоеИли", bitwise_or, "BitwiseOr"),
    ("ПобитовоеИсключительноеИли", bitwise_xor, "BitwiseXor"),
    ("ПобитовоеНе", bitwise_not, "BitwiseNot"),
    ("ПобитовоеИНе", bitwise_and_not, "BitwiseAndNot"),
    ("ПроверитьБит", check_bit, "CheckBit"),
    ("ПроверитьПоБитовойМаске", check_by_bit_mask, "CheckByBitMask"),
    ("УстановитьБит", set_bit, "SetBit"),
)
