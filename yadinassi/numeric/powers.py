"""Exact integral powers with explicit Yadinassi allocation limits.

The owner's native observations retain decimal coefficients for integral
exponents and use the existing division precision for Pow(3, -1). Fractional
exponents belong to the separate floating-point math implementation.
"""

from decimal import Decimal

from ..values import divide


# This is an implementation work/output budget, not a native Number limit.
_MAX_POWER_DIGITS = 4096


def _resource() -> ValueError:
    return ValueError("Pow: превышен предел ресурсов Yadinassi "
                      "(4096 десятичных разрядов)")


def _components(value: Decimal) -> tuple[int, tuple[int, ...], int]:
    """Remove trailing coefficient zeroes without consulting Decimal context."""
    sign, digits, exponent = value.as_tuple()
    end = len(digits)
    while end > 1 and digits[end - 1] == 0:
        end -= 1
        exponent += 1
    return sign, digits[:end], exponent


def _checked_power(coefficient: int, exponent: int, digits: int) -> int:
    """Check each multiplication before it can allocate an oversized result."""
    limit = 10 ** digits - 1
    result = 1
    while exponent:
        if exponent & 1:
            if result > limit // coefficient:
                raise _resource()
            result *= coefficient
        exponent >>= 1
        if exponent:
            if coefficient > limit // coefficient:
                raise _resource()
            coefficient *= coefficient
    return result


def integral_power(base: Decimal, exponent: Decimal) -> Decimal:
    """Compute a finite Decimal raised to an integral Decimal exponent.

    Positive powers are exact coefficient powers. Negative powers divide one
    by that exact result, retaining divide()'s nine-digit-block precision,
    resource checks and explicit rejection of unverified rounding ties.
    Both the intermediate positive power and final result must fit their
    respective budgets; a small reciprocal does not waive the work limit.
    No arithmetic here uses the caller's Decimal context or modifies flags.
    """
    if not isinstance(base, Decimal) or not isinstance(exponent, Decimal):
        raise TypeError("Pow: ожидаются числа")
    if not base.is_finite() or not exponent.is_finite():
        raise ValueError("Pow: ожидаются конечные числа")
    if exponent.is_zero():
        return Decimal(1)

    negative, exponent_digits, exponent_scale = _components(exponent)
    if exponent_scale < 0:
        raise ValueError("Pow: ожидается целый показатель степени")
    # Parity can be read even from an exponent such as 1E+1000000, without
    # expanding its million zeroes into a Python integer.
    odd = exponent_scale == 0 and exponent_digits[-1] % 2 == 1
    if base.is_zero():
        if negative:
            raise ValueError("Pow: ноль в отрицательной степени")
        return Decimal(0)
    if base == 1 or base == -1:
        return Decimal(-1 if base.is_signed() and odd else 1)

    sign, digits, scale = _components(base)
    if len(digits) > _MAX_POWER_DIGITS:
        raise _resource()
    # Every non-unit coefficient is >= 2, and 2**4 > 10. This deliberately
    # loose upper bound permits a tiny int conversion before exact checks.
    maximum = 4 * _MAX_POWER_DIGITS
    if scale:
        maximum = min(maximum, _MAX_POWER_DIGITS // abs(scale))
    if len(digits) > 1:
        # c**n has at least n*(digits(c)-1)+1 coefficient digits.
        maximum = min(maximum, (_MAX_POWER_DIGITS - 1) // (len(digits) - 1))
    if exponent.copy_abs() > maximum:
        raise _resource()
    power = int(exponent.copy_abs())
    result_scale = scale * power
    coefficient_digits = _MAX_POWER_DIGITS - max(result_scale, 0)
    if coefficient_digits < 1:
        raise _resource()

    coefficient = Decimal((0, digits, 0)).as_integer_ratio()[0]
    coefficient = _checked_power(coefficient, power, coefficient_digits)
    result = Decimal((int(bool(sign and odd)),
                      Decimal(coefficient).as_tuple().digits, result_scale))
    return divide(Decimal(1), result) if negative else result
