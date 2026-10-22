"""Finite native-confirmed character constants, not a new BSL value type."""

from dataclasses import dataclass
from types import MappingProxyType

from .values import BSLObject


# Native 1C 8.3.27.1508, PR80 run 39743653257: ordinary one-unit strings.
_MEMBERS = MappingProxyType({
    "вк": "\r", "cr": "\r",
    "втаб": "\v", "vtab": "\v",
    "нпп": "\u00a0", "nbsp": "\u00a0",
    "пс": "\n", "lf": "\n",
    "пф": "\f", "ff": "\f",
    "таб": "\t", "tab": "\t",
})


@dataclass(frozen=True, eq=False)
class BSLChars(BSLObject):
    """Closed read-only namespace; no constructor, reflection or iteration."""

    def __str__(self) -> str:
        raise ValueError("Строковое представление пространства Символы пока не поддерживается")

    def get_member(self, name: str) -> str:
        member = _MEMBERS.get(name.casefold())
        return super().get_member(name) if member is None else member


    def get_index(self, index: object) -> str:
        # PR80 run39746207974 measures the same twelve string keys/casing.
        if type(index) is not str:
            raise TypeError("Индекс Символы должен быть строкой")
        return self.get_member(index)

    def set_index(self, index: object, value: object) -> None:
        self.get_index(index)
        self.set_member(index, value)


CHARS = BSLChars()

__all__ = ["BSLChars", "CHARS"]
