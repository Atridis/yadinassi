"""Compatibility exports; use :mod:`yadinassi.numeric.math_conversion` for new code."""

from .numeric.math_conversion import (
    UnsupportedConversionRange,
    decimal_to_binary64,
)

__all__ = [
    "UnsupportedConversionRange",
    "decimal_to_binary64",
]
