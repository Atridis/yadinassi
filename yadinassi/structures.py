"""Named BSL collections with explicit properties, methods, and output slots."""

from dataclasses import dataclass
from decimal import Decimal

from .native_targets import LINUX_8_3_27_1508, current_native_target
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


def fill_property_values(target: object, source: object,
                         properties: object = None, exclude: object = None) -> None:
    """Bounded structure copy, including native-probed ordered selection lists."""
    # Exact built-in types keep extension hooks out of this bounded helper.
    if type(target) not in (BSLStructure, BSLFixedStructure):
        raise TypeError("ЗаполнитьЗначенияСвойств: приемник должен быть структурой")
    if type(source) not in (BSLStructure, BSLFixedStructure):
        raise TypeError("ЗаполнитьЗначенияСвойств: источник должен быть структурой")
    for value in (properties, exclude):
        if value is not None and type(value) is not str:
            raise TypeError("ЗаполнитьЗначенияСвойств: список свойств должен быть строкой")
    if properties is not None and exclude is not None:
        raise ValueError("Одновременные списки заполнения и исключения пока не поддерживаются")
    if type(target) is BSLFixedStructure:
        if properties is not None or exclude is not None:
            raise ValueError("Списки свойств для фиксированного приемника пока не поддерживаются")
        # Native 1C accepts this target without changing its immutable values.
        return

    def selected_names(value: str, *, reverse: bool = False):
        names = value.split(",")
        for name in reversed(names) if reverse else names:
            # Only Linux INCLUDE has measured empty-token/ASCII-space behavior.
            # Skip raw empties, not whitespace-only tokens; keep validation lazy.
            if reverse:
                if name == "":
                    continue
                name = name.strip(" ")
            # Windows INCLUDE, EXCLUDE and unmeasured Unicode whitespace retain
            # the conservative guard. A normalized empty token remains an error.
            if not name or name != trim_all(name):
                raise ValueError("Пустые имена или пробелы в списках свойств пока не поддерживаются")
            yield name, _key(name)

    if properties is not None:
        # Resolve and copy lazily, not in a validation pass: assignments survive
        # a later missing property. Linux 8.3.27.1508 probes traverse INCLUDE
        # right to left; the historical Windows checkpoint stays left to right.
        reverse = current_native_target() == LINUX_8_3_27_1508
        for name, key in selected_names(properties, reverse=reverse):
            if key not in target._items or key not in source._items:
                raise ValueError(f"Свойство структуры не найдено: {name}")
            target._items[key] = target._items[key][0], source._items[key][1]
        return

    excluded = set()
    if exclude is not None:
        for name, key in selected_names(exclude):
            if key not in target._items or key not in source._items:
                # EDT parameter/description disagree about source-only absence.
                # Do not invent mutation timing for this unprobed error path.
                raise ValueError("Отсутствующие исключаемые свойства пока не поддерживаются")
            excluded.add(key)
    for key, (name, _) in target._items.items():
        if key in source._items and key not in excluded:
            # Preserve target spelling and composition, and share value references.
            target._items[key] = name, source._items[key][1]
