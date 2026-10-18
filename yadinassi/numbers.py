"""Decimal numeric helpers; no binary floats or ambient-context rounding."""

from decimal import Decimal, ROUND_DOWN

from .values import number
from .round_modes import BSLRoundMode
from .collation import string_key


def integer_part(value: object) -> Decimal:
    value = number(value)
    # Unlike quantize or unary +, this preserves arbitrarily long integer
    # coefficients and ignores host precision, rounding, Inexact/Rounded traps.
    return value.to_integral_value(rounding=ROUND_DOWN)



def round_number(value: object, precision: object = Decimal(0),
                 mode: object = BSLRoundMode.ROUND15_AS20) -> Decimal:
    """Round decimal coefficients exactly, bounded by the input's digit count.

    Native PR25 confirms truncation of precision/numeric mode and symmetric
    tie rules. This does not impose inferred platform precision limits. Huge
    precision/mode inputs are compared as Decimal, never expanded to integers.
    """
    value = number(value)
    precision = number(precision).to_integral_value(rounding=ROUND_DOWN)
    if type(mode) is BSLRoundMode:
        increase_tie = mode is BSLRoundMode.ROUND15_AS20
    elif type(mode) is Decimal and mode.is_finite():
        increase_tie = not mode.to_integral_value(rounding=ROUND_DOWN).is_zero()
    else:
        raise TypeError("Окр: ожидается число или значение РежимОкругления")
    if value.is_zero():
        return Decimal(0)
    sign, digits, exponent = value.as_tuple()
    if precision >= -exponent:
        return value  # No padding or allocation proportional to requested precision.
    if precision < -value.adjusted() - 1:
        return Decimal(0)
    # Now conversion is bounded by the actual stored exponent, not user input.
    target_exponent = -int(precision)
    retained = len(digits) - (target_exponent - exponent)
    result = list(digits[:retained])
    first_discarded = digits[retained]
    increase = (first_discarded > 5 or
                (first_discarded == 5 and
                 (increase_tie or any(digits[retained + 1:]))))
    if increase:
        index = len(result) - 1
        while index >= 0 and result[index] == 9:
            result[index] = 0
            index -= 1
        if index < 0:
            result.insert(0, 1)
        else:
            result[index] += 1
    if not any(result):
        return Decimal(0)
    # Exact construction ignores host precision, rounding, exponent limits,
    # traps and flags. Applying the sign arithmetically would not be exact.
    return Decimal((sign, tuple(result), target_exponent))

def _extreme(first: object, rest: tuple[object, ...], *, maximum: bool) -> object:
    values = (first, *rest)
    if all(type(value) is str for value in values):
        # min/max retain the original first argument on equal collation keys.
        return (max if maximum else min)(values, key=string_key)
    numeric = all(type(value) in (Decimal, bool) for value in values)
    if not numeric:
        raise TypeError("Значения несовместимы для сравнения")
    if any(isinstance(value, Decimal) and not value.is_finite() for value in values):
        raise ValueError("Ожидается конечное число")
    result = first
    for value in rest:
        # Decimal compares exactly with bool (False=0, True=1). Return the
        # original winning object and retain the first object on equality.
        better = value > result if maximum else value < result
        if better:
            result = value
    return result


def minimum(first: object, *rest: object) -> object:
    return _extreme(first, rest, maximum=False)


def maximum(first: object, *rest: object) -> object:
    return _extreme(first, rest, maximum=True)


# A local allocation bound, not an inferred maximum width of a native Number.
# At most 4096 bits also fit the existing 4096-decimal-digit internal codec.
_MAX_RADIX_BITS = 4096


def _number_from_radix(value: object, *, base: int, prefix: str,
                       digits: str, name: str) -> Decimal:
    if type(value) is not str:
        raise TypeError(f"{name}: ожидается строка")
    maximum = _MAX_RADIX_BITS if base == 2 else _MAX_RADIX_BITS // 4
    if len(value) > maximum + 2:
        raise ValueError(f"{name}: превышен предел Yadinassi ({maximum} цифр)")
    if not value.startswith(prefix) or len(value) == 2:
        raise ValueError(f"{name}: недопустимое представление числа")
    # Do not use Python's permissive int grammar: reject signs, whitespace,
    # underscores, Unicode digits and uppercase prefixes before conversion.
    payload = value[2:]
    if any(character not in digits for character in payload):
        raise ValueError(f"{name}: недопустимое представление числа")
    # Both conversions are exact and ignore Decimal precision/traps/flags.
    # In particular, the owner-confirmed 39-digit uint128 must not be rounded.
    return Decimal(int(payload, base))


def number_from_binary_string(value: object) -> Decimal:
    return _number_from_radix(value, base=2, prefix="0b", digits="01",
                              name="ЧислоИзДвоичнойСтроки")


def number_from_hex_string(value: object) -> Decimal:
    return _number_from_radix(value, base=16, prefix="0x",
                              digits="0123456789abcdefABCDEF",
                              name="ЧислоИзШестнадцатеричнойСтроки")


BUILTINS = (("Цел", integer_part, "Int"), ("Мин", minimum, "Min"),
            ("Макс", maximum, "Max"), ("Окр", round_number, "Round"),
            ("ЧислоИзДвоичнойСтроки", number_from_binary_string, "NumberFromBinaryString"),
            ("ЧислоИзШестнадцатеричнойСтроки", number_from_hex_string, "NumberFromHexString"))
