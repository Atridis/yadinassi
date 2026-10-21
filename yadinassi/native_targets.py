"""Explicit, execution-scoped compatibility for native 1C checkpoints.

The host operating system and environment never select a target implicitly.
Python helpers outside an interpreter retain the original Windows behavior.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


WINDOWS_8_3_27_2342 = "windows-8.3.27.2342"
LINUX_8_3_27_1508 = "linux-8.3.27.1508"

_TARGETS = (WINDOWS_8_3_27_2342, LINUX_8_3_27_1508)


@dataclass(eq=False)
class _TargetScope:
    name: str
    parent: "_TargetScope | None"
    active: bool = True


_current_scope: ContextVar[_TargetScope | None] = ContextVar(
    "yadinassi_native_target", default=None)


def validate_native_target(name: str) -> str:
    """Accept only exact, supported target names, without aliases or coercion."""
    if type(name) is not str:
        raise TypeError("native_target must be a string")
    if name not in _TARGETS:
        raise ValueError(f"Unsupported native_target: {name!r}; expected one of {_TARGETS!r}")
    return name


def current_native_target() -> str:
    """Return the active execution target, or the historical Windows default."""
    scope = _current_scope.get()
    # A host callback may copy its context into detached asynchronous work.
    # Such a copy must not keep a completed interpreter execution alive.
    while scope is not None and not scope.active:
        scope = scope.parent
    return scope.name if scope is not None else WINDOWS_8_3_27_2342


@contextmanager
def target_context(name: str) -> Iterator[None]:
    """Temporarily select a target, restoring the caller on every exit path."""
    scope = _TargetScope(validate_native_target(name), _current_scope.get())
    token = _current_scope.set(scope)
    try:
        yield
    finally:
        scope.active = False
        _current_scope.reset(token)
