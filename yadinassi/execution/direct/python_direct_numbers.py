"""Numbers for closed direct modules: native integers and fractional Decimal.

Integer +, -, * intentionally use Python precision and ignore Decimal context.
Fractional operations retain Decimal context. Public scalar edges normalize once.
This does not authorize host, routine, or arbitrary collection numeric values.
"""
from decimal import Decimal
from yadinassi.execution.codegen.direct_scalar_semantics import decimal_divide, decimal_sign

def divide(left,right):
    if type(left) is int:left=Decimal(left)
    if type(right) is int:right=Decimal(right)
    return decimal_divide(left,right)

def sign(value,operator):
    if type(value) is int:
        if operator=='-' and value==0:return Decimal('-0')
        return -value if operator=='-' else value
    return decimal_sign(value,operator)

def public_number(value):
    return Decimal(value) if type(value) is int else value

_NEGATIVE_ZERO = Decimal('-0')
_REMAINDER_CONTEXT_BOUND = 10**38


def remainder(left,right):
    # Decimal remainder follows the dividend sign, unlike Python integer %.
    # Keep Decimal's precision error for large quotients and its zero-divisor
    # errors; neither condition belongs to the ordinary integer loop.
    if (type(left) is int and type(right) is int and right
            and -_REMAINDER_CONTEXT_BOUND < left < _REMAINDER_CONTEXT_BOUND):
        if left >= 0:
            return left % abs(right)
        magnitude = -left % abs(right)
        return -magnitude if magnitude else _NEGATIVE_ZERO
    if type(left) is int:left=Decimal(left)
    if type(right) is int:right=Decimal(right)
    return left % right
