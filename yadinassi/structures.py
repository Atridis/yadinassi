"""Named BSL collections with explicit properties, methods, and output slots."""

from dataclasses import dataclass
from decimal import Decimal

from .strings import trim_all
from .values import BSLFixedCollection, BSLObject, HostFunction, Reference


def _key(name: object) -> str:
    if not isinstance(name, str):
        raise TypeError("Имя свойства структуры должно быть строкой")
    if (not name or not (name[0].isalpha() or name[0] == "_")
            or not all(char.isalnum() or char == "_" for char in name)):
        raise ValueError(f"Недопустимое имя свойства структуры: {name}")
    return name.casefold()


@dataclass(frozen=True, eq=False)
class BSLKeyAndValue(BSLObject):
    key: object
    value: object

    def __str__(self) -> str:
        return "КлючИЗначение"

    def get_member(self, name: str) -> object:
        if name.casefold() in {"ключ", "key"}:
            return self.key
        if name.casefold() in {"значение", "value"}:
            return self.value
        return super().get_member(name)


class _StructureBase(BSLObject):
    def __iter__(self):
        version = self._version
        keys = iter(self._items)
        while True:
            # 1C leaves composition changes during enumeration undefined. Use a
            # catchable diagnostic rather than leak Python's dictionary errors.
            if version != self._version:
                raise ValueError("Изменение состава структуры во время обхода пока не поддерживается")
            try:
                key = next(keys)
            except StopIteration:
                return
            name, value = self._items[key]
            yield BSLKeyAndValue(name, value)

    def get(self, name: object) -> object:
        key = _key(name)
        if key not in self._items:
            raise ValueError(f"Свойство структуры не найдено: {name}")
        return self._items[key][1]

    def set(self, name: object, value: object) -> None:
        raise ValueError(f"Свойство фиксированной структуры недоступно для записи: {name}")

    def property(self, name: str, output: object = None) -> bool:
        # The native probe accepts surrounding U+0020 spaces for Property.
        # Other whitespace and other key-taking operations have no such evidence.
        key = _key(name.strip(" ") if isinstance(name, str) else name)
        found = key in self._items
        if isinstance(output, Reference):
            output.set(self._items[key][1] if found else None)
        return found

    def get_member(self, name: str) -> object:
        return self.get(name)

    def set_member(self, name: str, value: object) -> None:
        self.set(name, value)

    def get_method(self, name: str) -> object:
        methods = {
            "количество": lambda: Decimal(len(self._items)),
            "count": lambda: Decimal(len(self._items)),
            "свойство": self.property, "property": self.property,
        }
        key = name.casefold()
        method = methods.get(key)
        if method is None:
            raise ValueError(f"Метод структуры не найден: {name}")
        references = frozenset({1}) if key in {"свойство", "property"} else frozenset()
        return HostFunction(name, method, reference_parameters=references)


class BSLStructure(_StructureBase):
    def __init__(self, keys: object = "", *values: object):
        if isinstance(keys, BSLFixedStructure):
            if values:
                raise TypeError("Копирование структуры ожидает один аргумент")
            self._items = keys._items.copy()
            self._version = 0
            return
        if not isinstance(keys, str):
            raise TypeError("Список свойств структуры должен быть строкой")
        names = [name for part in keys.split(",") if (name := trim_all(part))]
        self._items: dict[str, tuple[str, object]] = {}
        self._version = 0
        for index, name in enumerate(names):
            self.insert(name, values[index] if index < len(values) else None)

    def __str__(self) -> str:
        return "Структура"

    def set(self, name: object, value: object) -> None:
        key = _key(name)
        if key not in self._items:
            raise ValueError(f"Свойство структуры не найдено: {name}")
        self._items[key] = self._items[key][0], value

    def insert(self, name: str, value: object = None) -> None:
        key = _key(name)
        if key not in self._items:
            self._version += 1
        # Native collections.bsl: Insert replaces the spelling as well as the
        # value. Ordinary property/index assignment still keeps the current name.
        self._items[key] = name, value

    def delete(self, name: str) -> None:
        key = _key(name)
        if key in self._items:
            del self._items[key]
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


class BSLFixedStructure(_StructureBase, BSLFixedCollection):
    def __init__(self, keys: object = "", *values: object):
        if isinstance(keys, BSLStructure):
            if values:
                raise TypeError("Копирование фиксированной структуры ожидает один аргумент")
            source = keys
        elif isinstance(keys, str):
            source = BSLStructure(keys, *values)
        else:
            raise TypeError("ФиксированнаяСтруктура ожидает строку свойств или структуру")
        self._items = source._items.copy()
        self._version = 0

    def __str__(self) -> str:
        return "ФиксированнаяСтруктура"
