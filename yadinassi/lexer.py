"""Compatibility exports; use :mod:`yadinassi.syntax.lexer` for new code."""

from .syntax.lexer import (
    KEYWORDS,
    EXECUTION_DIRECTIVES,
    Token,
    Lexer,
)

__all__ = [
    "KEYWORDS",
    "EXECUTION_DIRECTIVES",
    "Token",
    "Lexer",
]
