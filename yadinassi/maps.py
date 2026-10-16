"""BSL maps: typed scalar keys and identity keys for mutable objects."""

from decimal import Decimal

from .structures import BSLKeyAndValue
from .values import BSLObject, BSLType, HostFunction


def _key(value: object) -> tuple[type, object]:
    # Python considers True == Decimal(1). BSL keeps these types distinct.
    # Objects use identity, never Python's potentially mutable/unhashable value
    # semantics. Each entry retains the original object, so its id cannot be
    # reused while the entry exists.
    kind = type(value)
    if (kind is str or kind is bool or kind is Decimal or kind is type(None)
            or kind is BSLType):
        return kind, value
    # Even an extension's metaclass can override equality/hash, so do not put
    # arbitrary types into the token or compare them through tuple membership.
    return object, id(value)


class BSLMap(BSLObject):
    def __init__(self):
        self._items: dict[tuple[type, object], tuple[object, object]] = {}
        self._version = 0

    def __str__(self) -> str:
        return "Соответствие"

    def __iter__(self):
        version = self._version
        keys = iter(self._items)
        while True:
            # 1C does not promise order or safe composition changes during
            # traversal. Give a catchable subset diagnostic on the next advance.
            if version != self._version:
                raise ValueError("Изменение состава соответствия во время обхода пока не поддерживается")
            try:
                key = next(keys)
            except StopIteration:
                return
            yield BSLKeyAndValue(*self._items[key])

    def get(self, key: object) -> object:
        item = self._items.get(_key(key))
        return item[1] if item is not None else None

    def insert(self, key: object, value: object = None) -> None:
        token = _key(key)
        if token not in self._items:
            self._version += 1
        self._items[token] = key, value

    def set(self, key: object, value: object) -> None:
        self.insert(key, value)

    def delete(self, key: object) -> None:
        token = _key(key)
        if token in self._items:
            del self._items[token]
            self._version += 1

    def clear(self) -> None:
        if self._items:
            self._items.clear()
            self._version += 1

    def get_method(self, name: str) -> object:
        methods = {
            "вставить": self.insert, "insert": self.insert,
            "получить": self.get, "get": self.get,
            "удалить": self.delete, "delete": self.delete,
            "очистить": self.clear, "clear": self.clear,
            "количество": lambda: Decimal(len(self._items)),
            "count": lambda: Decimal(len(self._items)),
        }
        method = methods.get(name.casefold())
        if method is None:
            raise ValueError(f"Метод соответствия не найден: {name}")
        return HostFunction(name, method)
