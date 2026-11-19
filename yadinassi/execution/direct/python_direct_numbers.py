"""Numbers for closed direct modules: native integers and fractional Decimal.

Integer +, -, * intentionally use Python precision and ignore Decimal context.
Fractional operations retain Decimal context. Public scalar edges normalize once.
This does not authorize host, routine, or arbitrary collection numeric values.
"""
from decimal import Decimal
from yadinassi.execution.codegen.experimental_naked_scalar_semantics import decimal_divide, decimal_sign

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

def remainder(left,right):
    # Decimal remainder follows the dividend sign, unlike Python integer %.
    if type(left) is int:left=Decimal(left)
    if type(right) is int:right=Decimal(right)
    return left % right
