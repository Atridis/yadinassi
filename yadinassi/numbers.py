"""Decimal numeric helpers; no binary floats or ambient-context rounding."""

from decimal import Decimal, ROUND_DOWN

from .values import number
from .collation import string_key


def integer_part(value: object) -> Decimal:
    value = number(value)
    # Unlike quantize or unary +, this preserves arbitrarily long integer
    # coefficients and ignores host precision, rounding, Inexact/Rounded traps.
    return value.to_integral_value(rounding=ROUND_DOWN)


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


BUILTINS = (("Цел", integer_part, "Int"), ("Мин", minimum, "Min"),
            ("Макс", maximum, "Max"))
