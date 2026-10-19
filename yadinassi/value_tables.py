"""Bounded ValueTable operations evidenced by collections.out's table checkpoint.

Budgets are Yadinassi limits, not native platform limits. Sort and GroupBy
use bounded native-backed helpers; indexes and unprobed foreign-row schemas
deliberately remain unsupported.
"""
from decimal import Decimal, localcontext

from .structures import BSLStructure, _key
from .type_descriptions import BSLTypeDescription, _number_value
from .type_qualifiers import BSLAllowedLength
from .values import BSLArray, BSLObject, BSLType, HostFunction, NULL, equal

_MAX_CELLS = 1_000_000
_MAX_COLUMNS = 4096
_MAX_ROWS = 100_000
_MAX_TEXT = 1_000_000
_MAX_TOTAL_PRECISION = 16_384


def _integer(value):
    # Native table indices truncate, unlike Array indices.
    if type(value) is not Decimal or not value.is_finite():
        raise TypeError("ТаблицаЗначений: ожидается конечное число")
    if value.copy_abs() > 2 ** 32:
        raise ValueError("ТаблицаЗначений: число вне поддерживаемых границ")
    return int(value)


def _position(value, count, inserting=False):
    position = _integer(value)
    if inserting and not 0 <= position <= count:
        return count
    if not 0 <= position < count + int(inserting):
        raise IndexError("Индекс таблицы вне границ")
    return position


def _text(value):
    if type(value) is not str:
        raise TypeError("Ожидается строка")
    if len(value) > _MAX_TEXT:
        raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")
    return value


def _default(description):
    if description.types == (BSLType.STRING,):
        q = description.string_qualifiers
        if q.allowed_length is BSLAllowedLength.FIXED:
            if q.length > _MAX_TEXT:
                raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")
            return " " * int(q.length)
    return description.adjust_value()


def _adjust(description, value):
    if not description.types:
        return value  # Native untyped cells retain nested collections by identity.
    if description.types == (BSLType.NUMBER,) and value is NULL:
        return Decimal(0)
    if description.types == (BSLType.BOOLEAN,) and type(value) is str and value == "Истина":
        return True
    return description.adjust_value(value)


def _array(items):
    result = BSLArray()
    result.items = list(items)
    return result


def _method(name, methods):
    method = methods.get(name.casefold())
    if method is None:
        raise ValueError(f"Метод не найден: {name}")
    return HostFunction(name, method)


class BSLValueTableColumn(BSLObject):
    def __init__(self, table, name, value_type, title, width):
        self.table = table
        self.name = name
        self.value_type = value_type
        self.title = title
        self.width = width
        self._deleted = False

    def __str__(self):
        return "КолонкаТаблицыЗначений"

    def get_member(self, name):
        members = {"name": self.name, "имя": self.name,
                   "title": self.title, "заголовок": self.title,
                   "width": self.width, "ширина": self.width,
                   "valuetype": self.value_type, "типзначения": self.value_type}
        key = name.casefold()
        if key in members:
            return members[key]
        return super().get_member(name)

    def set_member(self, name, value):
        if self._deleted:
            raise ValueError("Колонка удалена")
        key = name.casefold()
        if key in ("name", "имя"):
            self.table.columns._validate_name(value, self)
            self.name = value
        elif key in ("title", "заголовок"):
            self.title = _text(value)
        elif key in ("width", "ширина"):
            self.width = Decimal(_integer(value) % (2 ** 32))
        else:
            super().set_member(name, value)


class BSLValueTableColumnCollection(BSLObject):
    def __init__(self, table):
        self.table = table
        self.items = []

    def __str__(self):
        return "КоллекцияКолонокТаблицыЗначений"

    def __iter__(self):
        return iter(self.items)

    def _validate_name(self, name, current=None):
        _text(name)
        if name:
            _key(name)
            if any(c is not current and c.name.casefold() == name.casefold()
                   for c in self.items):
                raise ValueError(f"Колонка уже существует: {name}")

    def find(self, name):
        name = _text(name).casefold()
        return next((c for c in self.items if c.name.casefold() == name), None)

    def get(self, index):
        return self.items[_position(index, len(self.items))]

    def get_index(self, index):
        if type(index) is str:
            column = self.find(index)
            if column is None:
                raise ValueError(f"Колонка не найдена: {index}")
            return column
        return self.get(index)

    def set_index(self, index, value):
        raise ValueError("Колонки таблицы недоступны для замены")

    def resolve(self, column):
        if type(column) is BSLValueTableColumn:
            if column.table is not self.table or column._deleted:
                raise ValueError("Колонка не принадлежит таблице")
            return column
        return self.get_index(column)

    def index_of(self, column):
        if type(column) is not BSLValueTableColumn:
            raise TypeError("Ожидается колонка таблицы")
        if column.table is self.table and column._deleted:
            return Decimal(2 ** 32 - 1)
        return Decimal(next((i for i, c in enumerate(self.items) if c is column), -1))

    def add(self, name="", value_type=None, title="", width=Decimal(0)):
        return self.insert(Decimal(len(self.items)), name, value_type, title, width)

    def insert(self, index, name="", value_type=None, title="", width=Decimal(0)):
        position = _position(index, len(self.items), True)
        self._validate_name(name)
        if value_type is None:
            value_type = BSLTypeDescription()
        if type(value_type) is not BSLTypeDescription:
            raise TypeError("Ожидается ОписаниеТипов")
        title = _text(title)
        width = Decimal(_integer(width) % (2 ** 32))
        self.table._budget(len(self.table.rows), len(self.items) + 1)
        default = _default(value_type)
        column = BSLValueTableColumn(self.table, name, value_type, title, width)
        self.items.insert(position, column)
        for row in self.table.rows:
            row.cells[column] = default
        return column

    def delete(self, column):
        column = self.resolve(column)
        self.items.remove(column)
        for row in self.table.rows:
            del row.cells[column]
        column._deleted = True
        column.name, column.title, column.width = "", "", Decimal(0)
        column.value_type = BSLTypeDescription()
        if not self.items:
            self.table.clear()

    def clear(self):
        for column in list(self.items):
            self.delete(column)
        self.table.clear()

    def move(self, column, offset):
        if type(column) not in (Decimal, BSLValueTableColumn):
            raise TypeError("Ожидается индекс или колонка таблицы")
        column = self.resolve(column)
        old = self.items.index(column)
        new = _position(Decimal(old + _integer(offset)), len(self.items))
        self.items.insert(new, self.items.pop(old))

    def get_member(self, name):
        return self.get_index(name)

    def get_method(self, name):
        return _method(name, {"count": lambda: Decimal(len(self.items)), "количество": lambda: Decimal(len(self.items)),
            "get": self.get, "получить": self.get, "find": self.find, "найти": self.find,
            "indexof": self.index_of, "индекс": self.index_of, "add": self.add, "добавить": self.add,
            "insert": self.insert, "вставить": self.insert, "delete": self.delete, "удалить": self.delete,
            "clear": self.clear, "очистить": self.clear, "move": self.move, "сдвинуть": self.move})


class BSLValueTableRow(BSLObject):
    def __init__(self, table):
        self.table = table
        self.cells = {c: _default(c.value_type) for c in table.columns.items}
        self._deleted = False

    def __str__(self):
        return "СтрокаТаблицыЗначений"

    def _live(self):
        if self._deleted:
            raise ValueError("Строка таблицы удалена")

    def __iter__(self):
        # Native detached rows enumerate their still-live owner table, even
        # though Owner/Get/member access remains invalid.
        if self._deleted:
            return iter(self.table.rows)
        return iter([self.cells[c] for c in self.table.columns.items])

    def owner(self):
        self._live()
        return self.table

    def get(self, index):
        self._live()
        return self.cells[self.table.columns.get(index)]

    def set(self, index, value):
        self._live()
        column = self.table.columns.get(index)
        self.cells[column] = _adjust(column.value_type, value)

    def get_index(self, index):
        self._live()
        return self.cells[self.table.columns.get_index(index)]

    def set_index(self, index, value):
        self._live()
        column = self.table.columns.get_index(index)
        self.cells[column] = _adjust(column.value_type, value)

    def get_member(self, name):
        return self.get_index(name)

    def set_member(self, name, value):
        self.set_index(name, value)

    def get_method(self, name):
        return _method(name, {"get": self.get, "получить": self.get,
            "set": self.set, "установить": self.set, "owner": self.owner, "владелец": self.owner})


class BSLValueTable(BSLObject):
    def __init__(self):
        self.rows = []
        self.columns = BSLValueTableColumnCollection(self)

    def __str__(self):
        return "ТаблицаЗначений"

    def __iter__(self):
        return iter(self.rows)

    @staticmethod
    def _budget(rows, columns):
        if rows > _MAX_ROWS or columns > _MAX_COLUMNS or rows * columns > _MAX_CELLS:
            raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")

    def get(self, index):
        return self.rows[_position(index, len(self.rows))]

    get_index = get

    def set_index(self, index, value):
        raise ValueError("Строки таблицы недоступны для замены")

    def add(self):
        return self.insert(Decimal(len(self.rows)))

    def insert(self, index):
        position = _position(index, len(self.rows), True)
        self._budget(len(self.rows) + 1, len(self.columns.items))
        row = BSLValueTableRow(self)
        self.rows.insert(position, row)
        return row

    def index_of(self, row):
        if type(row) is not BSLValueTableRow:
            raise TypeError("Ожидается строка таблицы")
        return Decimal(next((i for i, item in enumerate(self.rows) if item is row), -1))

    def _resolve_row(self, row):
        if type(row) is BSLValueTableRow:
            if row.table is not self or row._deleted:
                raise ValueError("Строка не принадлежит таблице")
            return row
        return self.get(row)

    def delete(self, row):
        row = self._resolve_row(row)
        self.rows.remove(row)
        row._deleted = True
        row.cells.clear()

    def clear(self):
        for row in self.rows:
            row._deleted = True
            row.cells.clear()
        self.rows.clear()

    def move(self, row, offset):
        row = self._resolve_row(row)
        old = self.rows.index(row)
        new = _position(Decimal(old + _integer(offset)), len(self.rows))
        self.rows.insert(new, self.rows.pop(old))

    def _selection(self, columns):
        if columns is None or (type(columns) is str and columns == ""):
            return list(self.columns.items)
        _text(columns)
        names = columns.split(",")
        if len(names) > _MAX_COLUMNS:
            raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")
        if any(not n or n != n.strip() for n in names):
            raise ValueError("Пустые имена и пробелы в списке колонок пока не поддерживаются")
        return [self.columns.get_index(name) for name in names]

    def find(self, value, columns=None):
        selected = self._selection(columns)
        return next((r for r in self.rows if any(equal(r.cells[c], value) for c in selected)), None)

    def find_rows(self, filters):
        if type(filters) is not BSLStructure:
            raise TypeError("Ожидается Структура отбора")
        if not filters._items:
            return _array([])
        selected = [(self.columns.get_index(name), value) for name, value in filters._items.values()]
        return _array(r for r in self.rows if all(equal(r.cells[c], v) for c, v in selected))

    def fill_values(self, value, columns=None):
        selected = self._selection(columns)  # Native validates names before mutation.
        for column in selected:
            adjusted = _adjust(column.value_type, value)
            for row in self.rows:
                row.cells[column] = adjusted

    def load_column(self, values, column):
        if type(values) is not BSLArray:
            raise TypeError("Ожидается Массив")
        column = self.columns.resolve(column)
        for row, value in zip(self.rows, values.items):
            row.cells[column] = _adjust(column.value_type, value)

    def unload_column(self, column):
        column = self.columns.resolve(column)
        return _array(row.cells[column] for row in self.rows)

    def total(self, column):
        column = self.columns.resolve(_text(column))
        types = column.value_type.types
        if len(types) > 1 and BSLType.NUMBER not in types:
            return None
        values = [r.cells[column] for r in self.rows]
        if len(types) == 1:
            values = [_number_value(v) if type(v) in (Decimal, str, bool) else Decimal(0) for v in values]
        else:
            values = [v for v in values if type(v) is Decimal]
        # Preserve exact sums independently of the ambient Decimal context.
        if not values:
            return Decimal(0)
        if any(not v.is_finite() or len(v.as_tuple().digits) > 4096 or abs(v.adjusted()) > 4096 for v in values):
            raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")
        # Coefficient length alone is insufficient: sparse values can span
        # thousands of places between their most and least significant digits.
        # Reserve decimal carry digits for the maximum number of addends.
        precision = max(v.adjusted() for v in values) - min(v.as_tuple().exponent for v in values) + 1 + len(str(len(values)))
        if precision > _MAX_TOTAL_PRECISION:
            raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")
        with localcontext() as ctx:
            ctx.prec = max(1, precision)
            ctx.Emax = 999999
            ctx.Emin = -999999
            return sum(values[1:], values[0])

    def sort(self, columns, comparator=None):
        from .value_table_sort import sort_table
        return sort_table(self, columns, comparator)

    def group_by(self, grouping_columns, totaling_columns=None):
        from .value_table_group import group_by
        return group_by(self, grouping_columns, totaling_columns)

    def copy_columns(self, columns=None):
        result = BSLValueTable()
        for column in self._selection(columns):
            result.columns.add(column.name, column.value_type, column.title, column.width)
        return result

    def copy(self, rows=None, columns=None):
        selected = self._selection(columns)
        if rows is None:
            source = self.rows
        elif type(rows) is BSLStructure:
            source = self.find_rows(rows).items
        elif type(rows) is BSLArray:
            source = rows.items
        else:
            raise TypeError("Ожидается Массив строк или Структура отбора")
        self._budget(len(source), len(selected))
        for row in source:
            if type(row) is not BSLValueTableRow:
                raise TypeError("Ожидается строка таблицы")
            row._live()
            # The native foreign-row probe has the same schema. Other schemas
            # cannot distinguish positional from name-based copying yet.
            if row.table is not self and [(c.name, c.value_type) for c in row.table.columns.items] != [(c.name, c.value_type) for c in self.columns.items]:
                raise ValueError("Копирование чужих строк другой схемы пока не поддерживается")
        result = self.copy_columns(columns)
        for old in source:
            new = result.add()
            for src, dst in zip(selected, result.columns.items):
                foreign = src if old.table is self else old.table.columns.items[self.columns.items.index(src)]
                new.cells[dst] = old.cells[foreign]
        return result

    def get_member(self, name):
        if name.casefold() in ("columns", "колонки"):
            return self.columns
        return super().get_member(name)

    def get_method(self, name):
        if name.casefold() in ("sort", "сортировать"):
            return HostFunction(name, self.sort, returns_value=False)
        if name.casefold() in ("groupby", "свернуть"):
            return HostFunction(name, self.group_by, returns_value=False)
        return _method(name, {"count": lambda: Decimal(len(self.rows)), "количество": lambda: Decimal(len(self.rows)),
            "get": self.get, "получить": self.get, "indexof": self.index_of, "индекс": self.index_of,
            "add": self.add, "добавить": self.add, "insert": self.insert, "вставить": self.insert,
            "delete": self.delete, "удалить": self.delete, "clear": self.clear, "очистить": self.clear,
            "move": self.move, "сдвинуть": self.move, "find": self.find, "найти": self.find,
            "findrows": self.find_rows, "найтистроки": self.find_rows, "fillvalues": self.fill_values,
            "заполнитьзначения": self.fill_values, "loadcolumn": self.load_column, "загрузитьколонку": self.load_column,
            "unloadcolumn": self.unload_column, "выгрузитьколонку": self.unload_column, "total": self.total,
            "итог": self.total, "copy": self.copy, "скопировать": self.copy,
            "copycolumns": self.copy_columns, "скопироватьколонки": self.copy_columns})
