"""Native-confirmed search directions and their read-only BSL namespace."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from .values import BSLObject


class BSLSearchDirection(Enum):
    """Opaque enum identities; numeric payloads are not numeric values."""

    FROM_BEGIN = 0
    FROM_END = 1

    def __str__(self) -> str:
        return "С начала" if self is BSLSearchDirection.FROM_BEGIN else "С конца"


_MEMBERS = {
    "сначала": BSLSearchDirection.FROM_BEGIN,
    "frombegin": BSLSearchDirection.FROM_BEGIN,
    "сконца": BSLSearchDirection.FROM_END,
    "fromend": BSLSearchDirection.FROM_END,
}


@dataclass(frozen=True, eq=False)
class BSLSearchDirections(BSLObject):
    """Expose only observed bilingual members, without host reflection."""

    def __str__(self) -> str:
        return "ПеречислениеНаправлениеПоиска"

    def __iter__(self) -> Iterator[BSLSearchDirection]:
        # The owner's search.enum.iteration probe establishes this order.
        return iter((BSLSearchDirection.FROM_BEGIN, BSLSearchDirection.FROM_END))

    def get_member(self, name: str) -> object:
        member = _MEMBERS.get(name.casefold())
        return super().get_member(name) if member is None else member


SEARCH_DIRECTIONS = BSLSearchDirections()

__all__ = ["BSLSearchDirection", "BSLSearchDirections", "SEARCH_DIRECTIONS"]
