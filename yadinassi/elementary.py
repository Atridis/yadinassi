"""Elementary math: native-observed decimal blocks and 15-digit results.

The input conversion model and exact integral powers are distinct from the
host binary64 transcendental functions. Native fixtures establish the sampled
results, not universal libm parity across all platforms and arguments.
"""

import math
from decimal import Decimal

from .values import number
from .powers import integral_power
from .binary_exp import binary_exp
from .math_conversion import UnsupportedConversionRange, decimal_to_binary64


def _result(value: float) -> Decimal:
    if not math.isfinite(value):
        raise ValueError("Математическая функция: результат вне диапазона")
    # Formatting and Decimal(string) ignore the caller's Decimal context.
    return Decimal(format(value, '.15g')) if value else Decimal(0)


def _unary(value: object, operation: str) -> Decimal:
    value = number(value)
    if operation == 'sqrt' and value < 0:
        raise ValueError("Sqrt: отрицательный аргумент")
    if operation in ('log', 'log10') and value <= 0:
        raise ValueError("Логарифм: аргумент должен быть положительным")
    if operation in ('asin', 'acos') and not Decimal(-1) <= value <= Decimal(1):
        raise ValueError("Аргумент вне диапазона [-1, 1]")
    binary = decimal_to_binary64(value)
    if operation in ('asin', 'acos') and not -1.0 <= binary <= 1.0:
        raise UnsupportedConversionRange(
            "Математика: блочное округление вышло за область функции; "
            "нативное поведение на этой границе пока не установлено")
    result = binary_exp(binary) if operation == 'exp' else getattr(math, operation)(binary)
    return _result(result)


def sqrt(value: object) -> Decimal:
    return _unary(value, 'sqrt')


def log(value: object) -> Decimal:
    return _unary(value, 'log')


def log10(value: object) -> Decimal:
    return _unary(value, 'log10')


def exp(value: object) -> Decimal:
    return _unary(value, 'exp')


def sin(value: object) -> Decimal:
    return _unary(value, 'sin')


def cos(value: object) -> Decimal:
    return _unary(value, 'cos')


def tan(value: object) -> Decimal:
    return _unary(value, 'tan')


def asin(value: object) -> Decimal:
    return _unary(value, 'asin')


def acos(value: object) -> Decimal:
    return _unary(value, 'acos')


def atan(value: object) -> Decimal:
    return _unary(value, 'atan')


def power(base: object, exponent: object) -> Decimal:
    base, exponent = number(base), number(exponent)
    if exponent == exponent.to_integral_value():
        return integral_power(base, exponent)
    if base < 0 or (base.is_zero() and exponent < 0):
        raise ValueError("Pow: аргументы вне области определения")
    return _result(math.pow(decimal_to_binary64(base), decimal_to_binary64(exponent)))


# These mathematical names are the same in both official language interfaces.
BUILTINS = tuple((name, function, name) for name, function in (
    ('Sqrt', sqrt), ('Log', log), ('Log10', log10), ('Exp', exp),
    ('Sin', sin), ('Cos', cos), ('Tan', tan), ('ASin', asin),
    ('ACos', acos), ('ATan', atan), ('Pow', power)))
