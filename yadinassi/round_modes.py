"""Opaque rounding modes and their explicit, read-only BSL namespace."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from .values import BSLObject


class BSLRoundMode(Enum):
    """Native enum identities, deliberately unrelated to numeric mode flags."""

    ROUND15_AS10 = 0
    ROUND15_AS20 = 1

    def __str__(self) -> str:
        return "Округлять 15 как 10" if self is BSLRoundMode.ROUND15_AS10 else "Округлять 15 как 20"


_MEMBERS = {
    "окр15как10": BSLRoundMode.ROUND15_AS10,
    "round15as10": BSLRoundMode.ROUND15_AS10,
    "окр15как20": BSLRoundMode.ROUND15_AS20,
    "round15as20": BSLRoundMode.ROUND15_AS20,
}


@dataclass(frozen=True, eq=False)
class BSLRoundModes(BSLObject):
    """Only the two observed enum members are exposed; no host reflection."""

    def __str__(self) -> str:
        return "ПеречислениеРежимОкругления"

    def __iter__(self) -> Iterator[BSLRoundMode]:
        # Explicit unique values, never the bilingual property dictionary.
        return iter((BSLRoundMode.ROUND15_AS10, BSLRoundMode.ROUND15_AS20))

    def get_member(self, name: str) -> object:
        member = _MEMBERS.get(name.casefold())
        return super().get_member(name) if member is None else member


ROUND_MODES = BSLRoundModes()

__all__ = ["BSLRoundMode", "BSLRoundModes", "ROUND_MODES"]
