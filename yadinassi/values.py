"""BSL values and explicit host API; Python attributes are never exposed."""

from decimal import Decimal
from typing import Callable


def to_string(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Да" if value else "Нет"
    if isinstance(value, Decimal):
        if value == 0:
            return "0"
        text = format(value, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, BSLArray):
        return "Массив"
    return str(value)


def number(value: object) -> Decimal:
    if isinstance(value, bool):
        return Decimal(int(value))
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
    return type(left) is type(right) and left == right


class BSLObject:
    """Subclass to expose a type through Interpreter.register_type()."""

    def get_member(self, name: str) -> object:
        raise ValueError(f"Метод или свойство не найдено: {name}")


class BSLArray(BSLObject):
    def __init__(self, size: Decimal = Decimal(0)):
        length = integer(size)
        if length < 0:
            raise ValueError("Размер массива не может быть отрицательным")
        self.items: list[object] = [None] * length

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
        self.items[self.checked_index(index)] = value

    def add(self, value: object) -> None:
        self.items.append(value)

    def insert(self, index: object, value: object) -> None:
        self.items.insert(self.checked_index(index, inserting=True), value)

    def delete(self, index: object) -> None:
        del self.items[self.checked_index(index)]

    def find(self, value: object) -> object:
        for index, item in enumerate(self.items):
            if equal(item, value):
                return Decimal(index)
        return None

    def get_member(self, name: str) -> object:
        methods = {
            "добавить": self.add, "add": self.add,
            "количество": lambda: Decimal(len(self.items)),
            "count": lambda: Decimal(len(self.items)),
            "вграница": lambda: Decimal(len(self.items) - 1),
            "ubound": lambda: Decimal(len(self.items) - 1),
            "получить": self.get, "get": self.get,
            "установить": self.set, "set": self.set,
            "вставить": self.insert, "insert": self.insert,
            "удалить": self.delete, "delete": self.delete,
            "очистить": self.items.clear, "clear": self.items.clear,
            "найти": self.find, "find": self.find,
        }
        method = methods.get(name.casefold())
        if method is None:
            return super().get_member(name)
        return HostFunction(name, method)


class HostFunction:
    """Only explicitly registered callables may be invoked from BSL."""

    def __init__(self, name: str, function: Callable):
        self.name = name
        self.function = function

    def __call__(self, *arguments: object) -> object:
        return self.function(*arguments)
