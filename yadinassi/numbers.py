"""Decimal numeric helpers; no binary floats or ambient-context rounding."""

from decimal import Decimal, ROUND_DOWN



def integer_part(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError("Цел: преобразование аргумента к числу пока не поддерживается")
    if not value.is_finite():
        raise ValueError("Ожидается конечное число")
    # Unlike quantize or unary +, this preserves arbitrarily long integer
    # coefficients and ignores host precision, rounding, Inexact/Rounded traps.
    return value.to_integral_value(rounding=ROUND_DOWN)


BUILTINS = (("Цел", integer_part, "Int"),)
