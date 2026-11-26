"""Numeric ABI differences for explicitly evidenced built-in operations."""
from functools import wraps

from yadinassi.numeric.bits import BUILTINS as BIT_BUILTINS
from .python_direct_numbers import public_number


BIT_IMPLEMENTATIONS = {id(function): function for _, function, _ in BIT_BUILTINS}


def bit_implementation(function):
    if id(function) not in BIT_IMPLEMENTATIONS:
        return function

    # test_bits: BSL's emitted int is a Number; the module's Python API still
    # rejects bare host int and non-number types.
    @wraps(function)
    def invoke(*arguments):
        return function(*map(public_number, arguments))

    return invoke
