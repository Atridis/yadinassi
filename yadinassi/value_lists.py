"""Bounded default-state ValueList operations from the owner core checkpoint.

Only Value, Presentation and Check are exposed on items. Typed constraints,
pictures and UI methods are deliberately outside this implementation. Sorting
uses the separate, bounded owner-confirmed ValueList sort checkpoint.
Resource budgets below are Yadinassi limits, not asserted native limits.
"""

from decimal import Decimal
import re
import weakref

from .type_descriptions import BSLTypeDescription
from .values import BSLArray, BSLObject, HostFunction, equal, to_string


_MAX_ITEMS = 100_000
_MAX_TEXT = 1_000_000
_MAX_NUMBER_DIGITS = 4096
_MAX_INTEGER = 2 ** 32
_MAX_ID = 2 ** 32


def _unsupported(message):
    raise ValueError(f"СписокЗначений: {message} пока не поддерживается в Yadinassi")


def _budget(message="превышен предел ресурсов"):
    raise ValueError(f"СписокЗначений: {message} Yadinassi")


def _integer(value, *, allow_boolean=False):
    """Observed method conversions; no generic host Number/String hooks."""
    kind = type(value)
    if kind is bool and allow_boolean:
        return int(value)
    if kind is str:
        if len(value) > _MAX_NUMBER_DIGITS:
            _budget()
        # Only integer text was observed; fractional/localized formats remain
        # distinct from the observed positive fractional Decimal conversion.
        if re.fullmatch(r"[+-]?[0-9]+", value) is None:
            _unsupported("этот формат числового аргумента")
        value = Decimal(value)
    elif kind is not Decimal:
        raise TypeError("СписокЗначений: ожидается число")
    if not value.is_finite():
        raise ValueError("СписокЗначений: ожидается конечное число")
    if (len(value.as_tuple().digits) > _MAX_NUMBER_DIGITS
            or value.copy_abs() > _MAX_INTEGER):
        _budget()
    if value < 0 and value != value.to_integral_value():
        _unsupported("отрицательный дробный числовой аргумент")
    return int(value)


def _position(value, count, *, inserting=False):
    position = _integer(value, allow_boolean=inserting)
    if not 0 <= position < count + int(inserting):
        raise IndexError("Индекс списка значений вне границ")
    return position


def _presentation(value):
    if value is None:
        return ""
    if type(value) is Decimal:
        value = to_string(value)
    if type(value) is not str:
        _unsupported("это преобразование представления")
    if len(value) > _MAX_TEXT:
        _budget()
    return value


def _check(value):
    if type(value) is bool:
        return value
    if type(value) is Decimal and value.is_finite() and value in (Decimal(0), Decimal(1)):
        return value == 1
    _unsupported("это преобразование пометки")


def _value(value):
    # Stored objects are references, never recursively traversed or copied.
    # Exact built-in types avoid invoking arbitrary extension equality hooks.
    from .type_values import _VALUE_TYPES
    if not any(type(value) is known for known, _, _ in _VALUE_TYPES):
        _unsupported("этот тип значения")
    if type(value) is Decimal:
        if not value.is_finite():
            raise ValueError("СписокЗначений: ожидается конечное число")
        if len(value.as_tuple().digits) > _MAX_NUMBER_DIGITS:
            _budget()
    if type(value) is str and len(value) > _MAX_TEXT:
        _budget()
    return value


class BSLValueListItem(BSLObject):
    """A live or detached item; an item does not keep its owner alive."""

    def __init__(self, owner, identifier, value=None, presentation="", check=False):
        self._owner_ref = weakref.ref(owner)
        self._id = identifier
        self._detached = False
        self._decoded_standalone = False
        self.value = value
        self.presentation = presentation
        self.check = check

    @classmethod
    def _from_stream(cls, identifier, value, presentation, check):
        """Internal factory for canonical fields validated by the codec reader.

        A standalone stream preserves its identifier field without reconstructing
        an owner. That wire field does not establish post-read GetID behavior.
        """
        item = object.__new__(cls)
        item._owner_ref = lambda: None
        item._id = identifier
        item._detached = False
        item._decoded_standalone = True
        item.value = value
        item.presentation = presentation
        item.check = check
        return item

    def __str__(self):
        if not self.presentation:
            _unsupported("строковое представление элемента с пустым Представлением")
        return self.presentation

    def get_id(self):
        if self._decoded_standalone:
            _unsupported("идентификатор отдельно восстановленного элемента")
        if self._detached:
            return Decimal(-1)
        owner = self._owner_ref()
        if owner is None:
            # The old observer's returned-item stream has -1 after release,
            # but this is not a direct GetID observation on a released owner.
            _unsupported("идентификатор элемента после освобождения списка")
        return Decimal(self._id if owner._by_id.get(self._id) is self else -1)

    def get_member(self, name):
        key = name.casefold()
        if key in {"value", "значение"}:
            return self.value
        if key in {"presentation", "представление"}:
            return self.presentation
        if key in {"check", "пометка"}:
            return self.check
        return super().get_member(name)

    def set_member(self, name, value):
        key = name.casefold()
        if key in {"value", "значение"}:
            self.value = _value(value)
        elif key in {"presentation", "представление"}:
            self.presentation = _presentation(value)
        elif key in {"check", "пометка"}:
            self.check = _check(value)
        else:
            super().set_member(name, value)

    def get_method(self, name):
        if name.casefold() in {"getid", "получитьидентификатор"}:
            return HostFunction(name, self.get_id)
        return super().get_method(name)


class BSLValueList(BSLObject):
    def __init__(self):
        self.items = []
        self._by_id = {}
        self._next_id = 0
        self._revision = 0
        self.value_type = BSLTypeDescription()

    def __str__(self):
        # Joining nonempty explicit presentations is directly observed. Do not
        # infer the native fallback for empty Presentation from String(Value).
        if not self.items:
            _unsupported("строковое представление пустого списка")
        if sum(len(item.presentation) + 2 for item in self.items) > _MAX_TEXT:
            _budget()
        return "; ".join(str(item) for item in self.items)

    def __iter__(self):
        expected = self._revision

        def iterate():
            position = 0
            while True:
                if expected != self._revision:
                    _unsupported("изменение коллекции во время активного обхода")
                if position >= len(self.items):
                    return
                yield self.items[position]
                position += 1

        return iterate()

    def count(self):
        return Decimal(len(self.items))

    def get(self, index):
        return self.items[_position(index, len(self.items))]

    def get_index(self, index):
        # Bracket access was observed with integral numeric indices only.
        if (type(index) is not Decimal or not index.is_finite()
                or index != index.to_integral_value()):
            _unsupported("это преобразование индекса в квадратных скобках")
        return self.get(index)

    def set_index(self, index, value):
        raise ValueError("Элементы списка значений недоступны для замены")

    def _allocation(self, count, *, replacing=False):
        if count + (0 if replacing else len(self.items)) > _MAX_ITEMS:
            _budget()
        if self._next_id + count > _MAX_ID:
            _budget("превышен предел идентификаторов")

    def _insert(self, position, value, presentation, check):
        self._allocation(1)
        value, presentation, check = _value(value), _presentation(presentation), _check(check)
        item = BSLValueListItem(self, self._next_id, value, presentation, check)
        self.items.insert(position, item)
        self._by_id[self._next_id] = item
        self._next_id += 1
        self._revision += 1
        return item

    def add(self, value=None, presentation="", check=False):
        return self._insert(len(self.items), value, presentation, check)

    def insert(self, index, value=None, presentation="", check=False):
        return self._insert(_position(index, len(self.items), inserting=True),
                            value, presentation, check)

    def index_of(self, item):
        if type(item) is not BSLValueListItem:
            raise TypeError("Ожидается элемент списка значений")
        if item._owner_ref() is not self or self._by_id.get(item._id) is not item:
            return Decimal(-1)
        return Decimal(self.items.index(item))

    def _selected_position(self, selector):
        if type(selector) is BSLValueListItem:
            position = int(self.index_of(selector))
            if position < 0:
                raise ValueError("Элемент не принадлежит списку значений")
            return position
        return _position(selector, len(self.items))

    def delete(self, selector):
        position = self._selected_position(selector)
        item = self.items.pop(position)
        del self._by_id[item._id]
        item._detached = True
        self._revision += 1

    def clear(self):
        for item in self.items:
            item._detached = True
        self.items.clear()
        self._by_id.clear()
        self._revision += 1

    def move(self, selector, offset):
        if type(selector) is BSLValueListItem and selector._owner_ref() is not self:
            # Owner records move.item and extra.foreign-move establish this
            # narrow case independently of the foreign item's ID, position,
            # value or deletion. Do not generalize the fallback to other
            # offsets/target sizes or to an item whose owner was released.
            if (selector._owner_ref() is None or len(self.items) not in (2, 3)
                    or type(offset) is not Decimal or not offset.is_finite()
                    or offset != 1):
                _unsupported("этот сдвиг чужого элемента")
            position, destination = 0, 1
        else:
            position = self._selected_position(selector)
            destination = position + _integer(offset)
        if not 0 <= destination < len(self.items):
            raise IndexError("Сдвиг элемента списка значений вне границ")
        if destination != position:
            item = self.items.pop(position)
            self.items.insert(destination, item)
            self._revision += 1

    def find_by_value(self, value):
        value = _value(value)
        return next((item for item in self.items if equal(item.value, value)), None)

    def find_by_id(self, identifier):
        return self._by_id.get(_integer(identifier))

    def fill_checks(self, check):
        check = _check(check)
        for item in self.items:
            item.check = check

    def copy(self):
        # Native Copy preserves current order and shared values, but allocates
        # independent items with fresh IDs, regardless of the source history.
        result = BSLValueList()
        for item in self.items:
            result.add(item.value, item.presentation, item.check)
        return result

    def load_values(self, values):
        if type(values) is not BSLArray:
            raise TypeError("ЗагрузитьЗначения ожидает Массив")
        self._allocation(len(values.items), replacing=True)
        # Validate and allocate the replacement before detaching any live item.
        for value in values.items:
            _value(value)
        items = [BSLValueListItem(self, self._next_id + index, value)
                 for index, value in enumerate(values.items)]
        by_id = {item._id: item for item in items}
        for item in self.items:
            item._detached = True
        self.items = items
        self._by_id = by_id
        self._next_id += len(items)
        self._revision += 1

    def unload_values(self):
        result = BSLArray()
        result.items = [item.value for item in self.items]
        return result

    def sort_by_value(self, direction=None):
        from .value_list_sort import sort_list
        sort_list(self, direction, by_presentation=False)

    def sort_by_presentation(self, direction=None):
        from .value_list_sort import sort_list
        sort_list(self, direction, by_presentation=True)

    def get_member(self, name):
        key = name.casefold()
        if key in {"valuetype", "типзначения"}:
            return self.value_type
        if key in {"availablevalues", "доступныезначения"}:
            return None
        return super().get_member(name)

    def set_member(self, name, value):
        if name.casefold() in {"valuetype", "типзначения", "availablevalues", "доступныезначения"}:
            _unsupported("изменение ограничений значений списка")
        super().set_member(name, value)

    def get_method(self, name):
        key = name.casefold()
        functions = {
            "count": self.count, "количество": self.count,
            "get": self.get, "получить": self.get,
            "add": self.add, "добавить": self.add,
            "insert": self.insert, "вставить": self.insert,
            "indexof": self.index_of, "индекс": self.index_of,
            "findbyvalue": self.find_by_value, "найтипозначению": self.find_by_value,
            "findbyid": self.find_by_id, "найтипоидентификатору": self.find_by_id,
            "copy": self.copy, "скопировать": self.copy,
            "unloadvalues": self.unload_values, "выгрузитьзначения": self.unload_values,
        }
        procedures = {
            "delete": self.delete, "удалить": self.delete,
            "clear": self.clear, "очистить": self.clear,
            "move": self.move, "сдвинуть": self.move,
            "loadvalues": self.load_values, "загрузитьзначения": self.load_values,
            "fillchecks": self.fill_checks, "заполнитьпометки": self.fill_checks,
            "sortbyvalue": self.sort_by_value,
            "сортироватьпозначению": self.sort_by_value,
            "sortbypresentation": self.sort_by_presentation,
            "сортироватьпопредставлению": self.sort_by_presentation,
        }
        if key in functions:
            return HostFunction(name, functions[key])
        if key in procedures:
            return HostFunction(name, procedures[key], returns_value=False)
        return super().get_method(name)
