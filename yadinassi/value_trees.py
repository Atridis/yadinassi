"""Bounded standalone ValueTree core; native edge semantics remain unverified.

No recursive host traversal, UI, codecs, transport, or database integration.
Limits apply to the whole tree, not independently to each child collection.
"""
from decimal import Decimal

from .values import BSLObject
from .type_descriptions import BSLTypeDescription
from .value_tables import (BSLValueTableColumn, BSLValueTableColumnCollection,
                           _default, _adjust, _method, _text)

_MAX_ROWS = 100_000
_MAX_COLUMNS = 4096
_MAX_CELLS = 1_000_000
_MAX_DEPTH = 256
_MAX_DEFAULT_TEXT = 1_000_000


def _position(value, count, inserting=False):
    # Reject unmeasured fractional/out-of-range coercions rather than borrowing
    # ValueTable's native-specific truncation and append-on-invalid-index rules.
    if type(value) is not Decimal or not value.is_finite() or value != value.to_integral_value():
        raise TypeError("ДеревоЗначений: ожидается целый индекс")
    if not 0 <= value < count + int(inserting):
        raise IndexError("Индекс дерева вне границ")
    return int(value)


class BSLValueTreeColumn(BSLObject):
    __init__ = BSLValueTableColumn.__init__
    def get_member(self, name):
        if name.casefold() not in {"name", "имя", "title", "заголовок", "width", "ширина", "valuetype", "типзначения"}:
            return super().get_member(name)
        if self._deleted:
            raise ValueError("Колонка дерева удалена")
        return BSLValueTableColumn.get_member(self, name)

    def set_member(self, name, value):
        if self._deleted:
            raise ValueError("Колонка дерева удалена")
        key = name.casefold()
        if key in ("name", "имя"):
            self.table.columns._validate_name(value, self)
            if value.casefold() in {"rows", "строки", "parent", "родитель"}:
                raise ValueError("Имя колонки совпадает со свойством строки дерева")
            self.name = value
        elif key in ("title", "заголовок"):
            self.title = _text(value)
        elif key in ("width", "ширина"):
            if type(value) is not Decimal or not value.is_finite() or value != value.to_integral_value() or not 0 <= value <= 2 ** 32 - 1:
                raise ValueError("ДеревоЗначений: ширина вне поддерживаемых границ")
            self.width = value
        else:
            super().set_member(name, value)

    def __str__(self):
        return "КолонкаДереваЗначений"


class BSLValueTreeColumnCollection(BSLObject):
    __init__ = BSLValueTableColumnCollection.__init__
    __iter__ = BSLValueTableColumnCollection.__iter__
    _validate_name = BSLValueTableColumnCollection._validate_name
    find = BSLValueTableColumnCollection.find
    get_member = BSLValueTableColumnCollection.get_member
    get_index = BSLValueTableColumnCollection.get_index
    set_index = BSLValueTableColumnCollection.set_index

    def __str__(self):
        return "КоллекцияКолонокДереваЗначений"

    def get(self, index):
        return self.items[_position(index, len(self.items))]

    def resolve(self, column):
        if type(column) is BSLValueTreeColumn:
            if column.table is not self.table or column._deleted or column not in self.items:
                raise ValueError("Колонка не принадлежит дереву")
            return column
        return self.get_index(column)

    def index_of(self, column):
        if type(column) is not BSLValueTreeColumn:
            raise TypeError("Ожидается колонка дерева")
        return Decimal(next((i for i, c in enumerate(self.items) if c is column), -1))

    def add(self, name="", value_type=None, title="", width=Decimal(0)):
        return self.insert(Decimal(len(self.items)), name, value_type, title, width)

    def insert(self, index, name="", value_type=None, title="", width=Decimal(0)):
        position = _position(index, len(self.items), True)
        self._validate_name(name)
        if name.casefold() in {"rows", "строки", "parent", "родитель"}:
            raise ValueError("Имя колонки совпадает со свойством строки дерева: пока не поддерживается")
        if value_type is None:
            value_type = BSLTypeDescription()
        if type(value_type) is not BSLTypeDescription:
            raise TypeError("Ожидается ОписаниеТипов")
        title = _text(title)
        if type(width) is not Decimal or not width.is_finite() or width != width.to_integral_value() or not 0 <= width <= 2 ** 32 - 1:
            raise ValueError("ДеревоЗначений: ширина вне поддерживаемых границ")
        self.table._budget(len(self.table._all_rows), len(self.items) + 1)
        default = _default(value_type)
        if (sum(len(c.default) for c in self.items if type(c.default) is str)
                + (len(default) if type(default) is str else 0) > _MAX_DEFAULT_TEXT):
            raise ValueError("ДеревоЗначений: превышен предел текста значений по умолчанию Yadinassi")
        column = BSLValueTreeColumn(self.table, name, value_type, title, width)
        column.default = default
        self.items.insert(position, column)
        for row in self.table._all_rows:
            row.cells[column] = default
        return column

    def delete(self, column):
        column = self.resolve(column)
        # Last-column lifetime is not established by a native checkpoint.
        if len(self.items) == 1 and self.table._all_rows:
            raise ValueError("Удаление последней колонки непустого дерева пока не подтверждено")
        self.items.remove(column)
        for row in self.table._all_rows:
            del row.cells[column]
        column._deleted = True

    def clear(self):
        if self.table._all_rows and self.items:
            raise ValueError("Очистка колонок непустого дерева пока не подтверждена")
        for column in self.items:
            column._deleted = True
        self.items.clear()

    def get_method(self, name):
        return _method(name, {"count": lambda: Decimal(len(self.items)), "количество": lambda: Decimal(len(self.items)),
            "get": self.get, "получить": self.get, "find": self.find, "найти": self.find,
            "indexof": self.index_of, "индекс": self.index_of, "add": self.add, "добавить": self.add,
            "insert": self.insert, "вставить": self.insert, "delete": self.delete, "удалить": self.delete,
            "clear": self.clear, "очистить": self.clear})


class BSLValueTreeRow(BSLObject):
    def __init__(self, collection):
        self.collection = collection
        self.tree = collection.tree
        self.parent = collection.parent
        self.depth = 0 if self.parent is None else self.parent.depth + 1
        # Immutable string defaults are shared; never allocate padded strings
        # once per row (which would bypass the bounded column-default budget).
        self.cells = {c: c.default if type(c.default) is str else _default(c.value_type)
                      for c in self.tree.columns.items}
        self.rows = BSLValueTreeRowCollection(self.tree, self)
        self._deleted = False

    def __str__(self):
        return "СтрокаДереваЗначений"

    def _live(self):
        if self._deleted:
            raise ValueError("Строка дерева удалена; доступ к отсоединенным строкам не поддерживается")

    def __iter__(self):
        self._live()
        return iter([self.cells[c] for c in self.tree.columns.items])

    def owner(self):
        self._live()
        return self.tree

    def level(self):
        self._live()
        return Decimal(self.depth)

    def get(self, index):
        self._live()
        return self.cells[self.tree.columns.get(index)]

    def set(self, index, value):
        self._live()
        column = self.tree.columns.get(index)
        self.cells[column] = _adjust(column.value_type, value)

    def get_index(self, index):
        self._live()
        return self.cells[self.tree.columns.get_index(index)]

    def set_index(self, index, value):
        self._live()
        column = self.tree.columns.get_index(index)
        self.cells[column] = _adjust(column.value_type, value)

    def get_member(self, name):
        self._live()
        if name.casefold() in ("rows", "строки"):
            return self.rows
        if name.casefold() in ("parent", "родитель"):
            return self.parent
        return self.get_index(name)

    def set_member(self, name, value):
        if name.casefold() in ("rows", "строки", "parent", "родитель"):
            raise ValueError("Свойство строки дерева недоступно для записи")
        self.set_index(name, value)

    def get_method(self, name):
        return _method(name, {"get": self.get, "получить": self.get,
            "set": self.set, "установить": self.set, "owner": self.owner, "владелец": self.owner,
            "level": self.level, "уровень": self.level})


class BSLValueTreeRowCollection(BSLObject):
    def __init__(self, tree, parent=None):
        self.tree = tree
        self.parent = parent
        self.items = []

    def __str__(self):
        return "КоллекцияСтрокДереваЗначений"

    def _live(self):
        if self.parent is not None:
            self.parent._live()

    def __iter__(self):
        self._live()
        return iter(self.items)

    def count(self):
        self._live()
        return Decimal(len(self.items))

    def get(self, index):
        self._live()
        return self.items[_position(index, len(self.items))]

    get_index = get

    def set_index(self, index, value):
        raise ValueError("Строки дерева недоступны для замены")

    def add(self):
        return self.insert(Decimal(len(self.items)))

    def insert(self, index):
        self._live()
        position = _position(index, len(self.items), True)
        self.tree._budget(len(self.tree._all_rows) + 1, len(self.tree.columns.items))
        if self.parent is not None and self.parent.depth + 1 > _MAX_DEPTH:
            raise ValueError("ДеревоЗначений: превышена глубина Yadinassi")
        row = BSLValueTreeRow(self)
        self.items.insert(position, row)
        self.tree._all_rows[row] = None
        return row

    def index_of(self, row):
        self._live()
        if type(row) is not BSLValueTreeRow:
            raise TypeError("Ожидается строка дерева")
        return Decimal(next((i for i, item in enumerate(self.items) if item is row), -1))

    def _remove_subtrees(self, roots):
        pending = list(roots)
        while pending:
            row = pending.pop()
            pending.extend(row.rows.items)
            row.rows.items.clear()
            row.cells.clear()
            row._deleted = True
            del self.tree._all_rows[row]

    def delete(self, row):
        self._live()
        if type(row) is not BSLValueTreeRow:
            row = self.get(row)
        if row.collection is not self or row._deleted:
            raise ValueError("Строка не принадлежит коллекции")
        self.items.remove(row)
        self._remove_subtrees([row])

    def clear(self):
        self._live()
        self._remove_subtrees(self.items)
        self.items.clear()

    def get_member(self, name):
        self._live()
        if name.casefold() in ("parent", "родитель"):
            return self.parent
        return super().get_member(name)

    def get_method(self, name):
        return _method(name, {"count": self.count, "количество": self.count,
            "get": self.get, "получить": self.get, "indexof": self.index_of, "индекс": self.index_of,
            "add": self.add, "добавить": self.add, "insert": self.insert, "вставить": self.insert,
            "delete": self.delete, "удалить": self.delete, "clear": self.clear, "очистить": self.clear})


class BSLValueTree(BSLObject):
    def __init__(self):
        self._all_rows = {}
        self.columns = BSLValueTreeColumnCollection(self)
        self.rows = BSLValueTreeRowCollection(self)

    def __str__(self):
        return "ДеревоЗначений"

    @staticmethod
    def _budget(rows, columns):
        if rows > _MAX_ROWS or columns > _MAX_COLUMNS or rows * columns > _MAX_CELLS:
            raise ValueError("ДеревоЗначений: превышен предел ресурсов Yadinassi")

    def get_member(self, name):
        if name.casefold() in ("columns", "колонки"):
            return self.columns
        if name.casefold() in ("rows", "строки"):
            return self.rows
        return super().get_member(name)
