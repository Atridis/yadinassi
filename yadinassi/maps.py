"""BSL maps: typed scalar keys and identity keys for collection/host objects."""

from decimal import Decimal

from .dates import BSLDate

from .structures import BSLKeyAndValue
from .values import BSLFixedCollection, BSLNull, BSLObject, BSLType, HostFunction


def _key(value: object) -> tuple[type, object]:
    # Python considers True == Decimal(1). BSL keeps these types distinct.
    # Objects use identity, never Python's potentially mutable/unhashable value
    # semantics. Each entry retains the original object, so its id cannot be
    # reused while the entry exists.
    kind = type(value)
    if kind is BSLDate:
        value.require_known()
        return kind, value.ticks
    if (kind is str or kind is bool or kind is Decimal or kind is type(None)
            or kind is BSLType or kind is BSLNull):
        return kind, value
    # Even an extension's metaclass can override equality/hash, so do not put
    # arbitrary types into the token or compare them through tuple membership.
    return object, id(value)


class _MapBase(BSLObject):
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

    def set(self, key: object, value: object) -> None:
        raise ValueError("Элементы фиксированного соответствия недоступны для записи")

    def get_method(self, name: str) -> object:
        methods = {
            "получить": self.get, "get": self.get,
            "количество": lambda: Decimal(len(self._items)),
            "count": lambda: Decimal(len(self._items)),
        }
        method = methods.get(name.casefold())
        if method is None:
            raise ValueError(f"Метод соответствия не найден: {name}")
        return HostFunction(name, method)


_NO_SOURCE = object()


class BSLMap(_MapBase):
    def __init__(self, source: object = _NO_SOURCE):
        if source is _NO_SOURCE:
            self._items: dict[tuple[type, object], tuple[object, object]] = {}
        elif isinstance(source, BSLFixedMap):
            self._items = source._items.copy()
        else:
            raise TypeError("Конструктор соответствия ожидает фиксированное соответствие")
        self._version = 0

    def __str__(self) -> str:
        return "Соответствие"

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
            "удалить": self.delete, "delete": self.delete,
            "очистить": self.clear, "clear": self.clear,
        }
        method = methods.get(name.casefold())
        if method is None:
            return super().get_method(name)
        return HostFunction(name, method)


class BSLFixedMap(_MapBase, BSLFixedCollection):
    def __init__(self, source: object):
        if not isinstance(source, BSLMap):
            raise TypeError("ФиксированноеСоответствие ожидает соответствие")
        self._items = source._items.copy()
        self._version = 0

    def get_index(self, key: object) -> object:
        # Unlike Get(), the native fixed-map indexer rejects an absent key.
        # Inspect entry presence, not its value: an existing Undefined is valid.
        item = self._items.get(_key(key))
        if item is None:
            raise ValueError("Ключ фиксированного соответствия не найден")
        return item[1]

    def __str__(self) -> str:
        return "ФиксированноеСоответствие"
