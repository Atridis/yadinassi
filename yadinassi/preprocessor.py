"""Compatibility exports; use :mod:`yadinassi.syntax.preprocessor` for new code."""

from .syntax.preprocessor import (
    DIRECTIVES,
    COMPILATION_PROFILES,
    validate_compilation_profile,
    OPERATORS,
    REGION_DIRECTIVES,
    ConditionalCompilation,
    SourceRegions,
)

__all__ = [
    "DIRECTIVES",
    "COMPILATION_PROFILES",
    "validate_compilation_profile",
    "OPERATORS",
    "REGION_DIRECTIVES",
    "ConditionalCompilation",
    "SourceRegions",
]
