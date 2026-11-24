"""Exact numeric offsets for supported mutable BSL Array operations."""

from decimal import Decimal


def array_offset(items, index, *, method=False):
    kind = type(index)
    if kind is Decimal:
        # Check before int(), including huge values and nonfinite Decimals.
        # A named method truncates before checking the lower bound.
        size = list.__len__(items)
        if size and index.is_finite() and index < size and (index > -1 if method else index >= 0):
            return int(index)
    elif kind is int or (method and kind is bool):
        if 0 <= index < list.__len__(items):
            return int(index)
    else:
        raise TypeError('Ожидается число')
    raise IndexError(f'Индекс массива вне границ: {index}')
