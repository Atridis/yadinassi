"""Empirical decimal-to-binary conversion for elementary math functions."""

from decimal import Decimal
import math


# A local implementation envelope, not an inferred native Number limit.
# Both the unscaled coefficient and 10**306 remain finite binary64 values.
_MAX_COEFFICIENT_DIGITS = 306
_MAX_SCALE_BLOCKS = 34
_BLOCK_BASE = 1_000_000_000.0


class UnsupportedConversionRange(ValueError):
    """Conversion would need an unverified extreme-scale strategy."""


def decimal_to_binary64(value: Decimal) -> float:
    """Normalize base-1e9 blocks, Horner accumulate, then scale once.

    The native math checkpoints distinguish this order from float(Decimal),
    converting the entire coefficient at once, accumulating from the right,
    dividing by 1e9 repeatedly, or multiplying by a reciprocal. In particular,
    independent Tan/Cos and Exp boundary observations support the same model.

    This is an empirical conversion model, not a claim of universal native
    parity. Extreme coefficients and scales fail explicitly before expansion
    or intermediate overflow; there is no guessed alternative conversion.
    """
    if type(value) is not Decimal or not value.is_finite():
        raise ValueError("Математика: ожидается конечное число")
    if value.is_zero():
        return 0.0

    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
        exponent += 1
    block_exponent, padding = divmod(exponent, 9)
    coefficient_length = end + padding
    if (coefficient_length > _MAX_COEFFICIENT_DIGITS
            or abs(block_exponent) > _MAX_SCALE_BLOCKS):
        raise UnsupportedConversionRange(
            "Математика: преобразование за пределами поддержанного диапазона "
            "Yadinassi (306 разрядов коэффициента или масштаба); "
            "нативное поведение в этой области пока не установлено")

    # The input's exponent cannot cause unbounded zero-padding or integer
    # construction. Each parsed chunk has at most nine decimal digits.
    text = ''.join(str(digit) for digit in digits[:end]) + '0' * padding
    first = len(text) % 9 or 9
    result = float(int(text[:first]))
    for offset in range(first, len(text), 9):
        result = result * _BLOCK_BASE + int(text[offset:offset + 9])

    if block_exponent < 0:
        result /= float(10 ** (-9 * block_exponent))
    elif block_exponent > 0:
        result *= float(10 ** (9 * block_exponent))
    if not math.isfinite(result):
        raise UnsupportedConversionRange(
            "Математика: переполнение преобразования в двоичное число; "
            "нативное поведение для такого входа пока не установлено")
    return -result if sign else result
