"""BSL values and explicit host API; Python attributes are never exposed."""

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import re
from typing import Callable


class BSLType(Enum):
    """Opaque, immutable type identities; presentations are not their identity."""

    UNDEFINED = "Неопределено"
    BOOLEAN = "Булево"
    NUMBER = "Число"
    STRING = "Строка"
    ARRAY = "Массив"
    STRUCTURE = "Структура"
    MAP = "Соответствие"
    FIXED_ARRAY = "ФиксированныйМассив"
    FIXED_STRUCTURE = "ФиксированнаяСтруктура"
    FIXED_MAP = "ФиксированноеСоответствие"
    KEY_AND_VALUE = "КлючИЗначение"
    TYPE = "Тип"

    def __str__(self) -> str:
        return self.value


def to_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        text = format(value, "f")
        text = text.rstrip("0").rstrip(".") if "." in text else text
        # The owner's native numbers.out confirms a decimal comma and groups
        # of three integer digits separated by U+00A0 (not an ASCII space).
        # Literal syntax and canonical Number("1.5") input remain dot-based.
        integer, separator, fraction = text.partition(".")
        sign = "-" if integer.startswith("-") else ""
        digits = integer[len(sign):]
        groups = [digits[max(0, end - 3):end] for end in range(len(digits), 0, -3)]
        result = sign + "\u00a0".join(reversed(groups))
        return result + ("," + fraction if separator else "")
    if isinstance(value, BSLArray):
        return "Массив"
    return str(value)


def number(value: object) -> Decimal:
    if isinstance(value, bool):
        return Decimal(int(value))
    if isinstance(value, str) and ("," in value or "\u00a0" in value):
        # Accept this standalone presentation as well as canonical input.
        # Localized groups are exactly three ASCII digits with U+00A0; mixed
        # separators and other grouping conventions are not guessed.
        value = value.strip()
        if "\u00a0" in value:
            pattern = r"[+-]?[0-9]{1,3}(?:\u00a0[0-9]{3})+(?:,[0-9]+)?"
        elif "," in value:
            pattern = r"[+-]?[0-9]+,[0-9]+"
        else:
            pattern = None  # Only surrounding whitespace was localized.
        if pattern is not None and re.fullmatch(pattern, value) is None:
            raise ValueError("Невозможно преобразовать значение в число")
        value = value.replace("\u00a0", "").replace(",", ".")
    if isinstance(value, (str, Decimal, int)):
        result = Decimal(value)
        if result.is_finite():
            return result
    raise ValueError("Невозможно преобразовать значение в число")


def require_number(value: object) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError("Ожидается число")
    return value


def boolean(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return value != 0
    raise TypeError("Ожидается булево значение или число")


def integer(value: object) -> int:
    value = require_number(value)
    if value != value.to_integral_value():
        raise ValueError("Ожидается целое число")
    return int(value)


def equal(left: object, right: object) -> bool:
    # Python equates True and 1; BSL values keep their types.
    if type(left) is not type(right):
        return False
    if issubclass(type(left), BSLFixedCollection):
        # Native collections compare by identity, even for equal contents.
        # Do not let a host subclass replace this with Python value equality.
        return left is right
    return left == right


class BSLObject:
    """Subclass to expose a type through Interpreter.register_type()."""

    def get_member(self, name: str) -> object:
        raise ValueError(f"Метод или свойство не найдено: {name}")

    def get_method(self, name: str) -> object:
        # Existing extensions expose methods through get_member. Collections with
        # dynamic properties can override this to keep method names independent.
        return self.get_member(name)

    def set_member(self, name: str, value: object) -> None:
        raise ValueError(f"Свойство недоступно для записи: {name}")


class BSLFixedCollection:
    """Marker for fixed collections with identity comparison semantics."""


class _ArrayBase(BSLObject):
    """Shared reads; fixed arrays do not inherit any mutable collection API."""

    def __iter__(self):
        return iter(self.items)

    def checked_index(self, index: object, *, inserting: bool = False) -> int:
        value = integer(index)
        limit = len(self.items) + int(inserting)
        if not 0 <= value < limit:
            raise IndexError(f"Индекс массива вне границ: {value}")
        return value

    def get(self, index: object) -> object:
        return self.items[self.checked_index(index)]

    def set(self, index: object, value: object) -> None:
        raise ValueError("Элементы фиксированного массива недоступны для записи")

    def find(self, value: object) -> object:
        for index, item in enumerate(self.items):
            if equal(item, value):
                return Decimal(index)
        return None

    def get_member(self, name: str) -> object:
        methods = {
            "количество": lambda: Decimal(len(self.items)),
            "count": lambda: Decimal(len(self.items)),
            "вграница": lambda: Decimal(len(self.items) - 1),
            "ubound": lambda: Decimal(len(self.items) - 1),
            "получить": self.get, "get": self.get,
            "найти": self.find, "find": self.find,
        }
        method = methods.get(name.casefold())
        if method is None:
            return super().get_member(name)
        return HostFunction(name, method)


class BSLArray(_ArrayBase):
    def __init__(self, size: object = Decimal(0)):
        if isinstance(size, BSLFixedArray):
            # The platform recursively converts direct fixed-array elements.
            self.items = [BSLArray(item) if isinstance(item, BSLFixedArray) else item
                          for item in size.items]
            return
        length = integer(size)
        if length < 0:
            raise ValueError("Размер массива не может быть отрицательным")
        self.items: list[object] = [None] * length

    def set(self, index: object, value: object) -> None:
        self.items[self.checked_index(index)] = value

    def add(self, value: object) -> None:
        self.items.append(value)

    def insert(self, index: object, value: object) -> None:
        self.items.insert(self.checked_index(index, inserting=True), value)

    def delete(self, index: object) -> None:
        del self.items[self.checked_index(index)]

    def get_member(self, name: str) -> object:
        methods = {
            "добавить": self.add, "add": self.add,
            "установить": self.set, "set": self.set,
            "вставить": self.insert, "insert": self.insert,
            "удалить": self.delete, "delete": self.delete,
            "очистить": self.items.clear, "clear": self.items.clear,
        }
        method = methods.get(name.casefold())
        if method is None:
            return super().get_member(name)
        return HostFunction(name, method)


class BSLFixedArray(_ArrayBase, BSLFixedCollection):
    def __init__(self, source: object):
        if not isinstance(source, BSLArray):
            raise TypeError("ФиксированныйМассив ожидает массив")
        self.items = self._freeze_items(source, set())

    @staticmethod
    def _freeze_items(source: BSLArray, active: set[int]) -> tuple[object, ...]:
        # Follow direct mutable-array elements only. Records, maps and already
        # fixed arrays retain their references; their contents are not traversed.
        # Native cycle behavior is unverified: reject a cycle explicitly rather
        # than recurse until the host stack overflows. Repeated acyclic branches
        # are copied independently, without treating sharing as a cycle.
        identity = id(source)
        if identity in active:
            raise ValueError("ФиксированныйМассив с циклическими вложенными массивами "
                             "пока не поддерживается")
        active.add(identity)
        try:
            items = []
            for item in source.items:
                if isinstance(item, BSLArray):
                    snapshot = object.__new__(BSLFixedArray)
                    snapshot.items = BSLFixedArray._freeze_items(item, active)
                    item = snapshot
                items.append(item)
            return tuple(items)
        finally:
            active.remove(identity)

    def __str__(self) -> str:
        return "ФиксированныйМассив"


@dataclass
class Reference:
    """A caller-owned storage location; never exposed as a BSL object."""

    get: Callable[[], object]
    set: Callable[[object], None]


class HostFunction:
    """Only explicitly registered callables may be invoked from BSL."""

    def __init__(self, name: str, function: Callable, *,
                 reference_parameters: frozenset[int] = frozenset()):
        self.name = name
        self.function = function
        self.reference_parameters = reference_parameters

    def __call__(self, *arguments: object) -> object:
        return self.function(*arguments)
