"""Compatibility exports; use :mod:`yadinassi.syntax.parser` for new code."""

from .syntax.parser import (
    PRECEDENCE,
    Parser,
    validate_async,
    validate_labels,
    parse,
    parse_expression,
    parse_fragment,
)

__all__ = [
    "PRECEDENCE",
    "Parser",
    "validate_async",
    "validate_labels",
    "parse",
    "parse_expression",
    "parse_fragment",
]
