"""Native-confirmed sort directions and their read-only BSL namespace."""

from dataclasses import dataclass
from enum import Enum
from typing import Iterator

from .values import BSLObject


class BSLSortDirection(Enum):
    """Opaque enum identities; numeric payloads are not numeric values."""

    ASC = 0
    DESC = 1

    def __str__(self) -> str:
        return "По возрастанию" if self is BSLSortDirection.ASC else "По убыванию"


_MEMBERS = {
    "возр": BSLSortDirection.ASC,
    "asc": BSLSortDirection.ASC,
    "убыв": BSLSortDirection.DESC,
    "desc": BSLSortDirection.DESC,
}


@dataclass(frozen=True, eq=False)
class BSLSortDirections(BSLObject):
    """Expose only observed bilingual members, without host reflection."""

    def __str__(self) -> str:
        return "ПеречислениеНаправлениеСортировки"

    def __iter__(self) -> Iterator[BSLSortDirection]:
        # The owner's table.list.sort.enum.identity establishes this order.
        return iter((BSLSortDirection.ASC, BSLSortDirection.DESC))

    def get_member(self, name: str) -> object:
        member = _MEMBERS.get(name.casefold())
        return super().get_member(name) if member is None else member


SORT_DIRECTIONS = BSLSortDirections()

__all__ = ["BSLSortDirection", "BSLSortDirections", "SORT_DIRECTIONS"]
