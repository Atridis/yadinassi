"""Bounded standalone ValueTree core; native edge semantics remain unverified.

No recursive host traversal, UI, codecs, transport, or database integration.
Limits apply to the whole tree, not independently to each child collection.
"""
from decimal import Context, Decimal, DecimalException, InvalidOperation, MAX_EMAX, MIN_EMIN, Overflow, ROUND_DOWN, Rounded

from .values import BSLArray, BSLObject, NULL, equal
from .structures import BSLStructure
from .type_descriptions import BSLTypeDescription, _boolean_value, _number_value, _MAX_NUMBER_DIGITS
from .value_tables import (BSLValueTableColumn, BSLValueTableColumnCollection,
                           _default, _adjust, _method, _text)

_MAX_ROWS = 100_000
_MAX_COLUMNS = 4096
_MAX_CELLS = 1_000_000
_MAX_DEPTH = 256
_MAX_DEFAULT_TEXT = 1_000_000
_MAX_SEARCH_WORK = 8_000_000
_MAX_SEARCH_TEXT = 1_000_000


class _SearchBudget:
    """Local logical-work limit, not a native platform limit."""
    def __init__(self):
        self.remaining = _MAX_SEARCH_WORK

    def charge(self, units):
        if units > self.remaining:
            raise ValueError("ДеревоЗначений: превышен предел работы поиска Yadinassi")
        self.remaining -= units


def _search_scalar(value, budget):
    # Identity-only type gates: even type membership/equality can call an
    # extension metaclass. Unknown objects never supply conversion/equality.
    kind = type(value)
    if value is None or value is NULL or kind is bool:
        units = 1
    elif kind is str:
        units = max(1, len(value))
        if units > _MAX_SEARCH_TEXT:
            raise ValueError("ДеревоЗначений: превышен предел текста поиска Yadinassi")
    elif kind is Decimal:
        # Reserve before coefficient inspection/conversion. A bounded Decimal
        # context first rejects oversized coefficients without materializing an
        # arbitrarily large Python digits tuple (including trailing zeroes).
        reserve = 3 * _MAX_NUMBER_DIGITS
        budget.charge(reserve)
        if not value.is_finite():
            raise ValueError("ДеревоЗначений: ожидается конечное число поиска")
        try:
            context = Context(prec=_MAX_NUMBER_DIGITS, Emax=MAX_EMAX, Emin=MIN_EMIN,
                              traps=[Rounded, InvalidOperation, Overflow])
            # Scale only the temporary validation value, so extreme exponents
            # neither expand text nor underflow an otherwise bounded coefficient.
            context.scaleb(value, -value.adjusted())
        except DecimalException:
            raise ValueError("ДеревоЗначений: число вне ресурсных границ поиска") from None
        _number_value(value)  # Existing validated converter, now size-bounded.
        units = len(value.as_tuple().digits)
        budget.remaining += reserve - 3 * units
        return units
    else:
        raise TypeError("ДеревоЗначений: этот тип значения поиска пока не поддерживается")
    budget.charge(units)
    return units


def _search_name(name, budget):
    if type(name) is not str:
        raise TypeError("ДеревоЗначений: ожидается имя колонки")
    _search_scalar(name, budget)  # Charge before casefold, not after its work.
    key = name.casefold()
    _search_scalar(key, budget)  # Charge before hashing/comparing normalized text.
    return key


def _search_recursive(value, budget):
    # Undefined differs from omission here, unlike TypeDescription's converter.
    kind = type(value)
    if value is None or value is NULL or not (kind is bool or kind is Decimal or kind is str):
        raise TypeError("ДеревоЗначений: неподдерживаемый флаг поиска")
    units = _search_scalar(value, budget)
    if kind is str and value != "True":
        raise ValueError("ДеревоЗначений: неподдерживаемый строковый флаг поиска")
    # Number 1 and String True were measured for FindRows. Other bounded finite
    # Decimal flags use the separately evidenced converter as a local extension,
    # not a claim that all native FindRows flag coercions have been established.
    budget.charge(units)  # Converter repeats number validation/string comparison.
    return _boolean_value(value)


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

    def find(self, value, columns="", recursive=False):
        """First scalar match in row-major, optionally depth-first hierarchy order."""
        self._live()
        budget = _SearchBudget()
        query_units = _search_scalar(value, budget)
        # Only the two measured scalar forms extend the Boolean domain here.
        # Keep FindRows' separately documented converter policy unchanged.
        if type(recursive) is not bool:
            kind = type(recursive)
            if kind is not Decimal and kind is not str:
                raise TypeError("ДеревоЗначений: неподдерживаемый флаг поиска")
            _search_scalar(recursive, budget)  # Before equality, including sNaN.
            if not ((kind is Decimal and recursive == Decimal(1))
                    or (kind is str and recursive == "True")):
                raise ValueError("ДеревоЗначений: неизмеренный флаг поиска")
            recursive = True
        if columns is None:
            columns = ""
        if type(columns) is not str:
            raise TypeError("ДеревоЗначений: ожидается список имен колонок")
        _search_scalar(columns, budget)  # Bound before splitting or stripping.
        if type(self.tree.columns.items) is not list or type(self.items) is not list:
            raise ValueError("Неверная коллекция поиска дерева")
        if len(self.tree.columns.items) > _MAX_COLUMNS or columns.count(',') >= _MAX_COLUMNS:
            raise ValueError("ДеревоЗначений: превышен предел колонок поиска Yadinassi")
        schema = {}
        for column in self.tree.columns.items:
            if type(column) is not BSLValueTreeColumn or column.table is not self.tree or column._deleted:
                raise ValueError("Колонка не принадлежит дереву поиска")
            schema[_search_name(column.name, budget)] = column
        if columns == "":
            selected = list(self.tree.columns.items)
        else:
            names = []
            for part in columns.split(','):
                name = part.strip()
                if name:
                    names.append(name)
            if not names:
                raise ValueError("ДеревоЗначений: пустой список имен пока не поддерживается")
            selected = []
            seen = set()
            for name in names:
                column = schema.get(_search_name(name, budget))
                if column is None:
                    raise ValueError("Колонка поиска дерева не найдена")
                # Duplicate names do not repeat work or alter row selection.
                if id(column) not in seen:
                    seen.add(id(column))
                    selected.append(column)
        if not selected:
            return None
        pending = [(self, iter(self.items))]
        visited = cells = 0
        while pending:
            collection, iterator = pending[-1]
            try:
                row = next(iterator)
            except StopIteration:
                pending.pop()
                continue
            visited += 1
            cells += len(selected)
            if visited > _MAX_ROWS or cells > _MAX_CELLS:
                raise ValueError("ДеревоЗначений: превышен предел ресурсов поиска Yadinassi")
            budget.charge(1)
            if type(row) is not BSLValueTreeRow or row.tree is not self.tree or row.collection is not collection:
                raise ValueError("Строка не принадлежит коллекции поиска дерева")
            row._live()
            if type(row.cells) is not dict:
                raise ValueError("Неверные ячейки строки поиска дерева")
            if type(row.depth) is not int or not 0 <= row.depth <= _MAX_DEPTH:
                raise ValueError("ДеревоЗначений: превышена глубина поиска Yadinassi")
            values = []
            for column in selected:
                cell = row.cells[column]
                _search_scalar(cell, budget)
                budget.charge(query_units)
                values.append(cell)
            if any(equal(cell, value) for cell in values):
                return row
            if recursive:
                children = row.rows
                if (type(children) is not BSLValueTreeRowCollection
                        or children.tree is not self.tree or children.parent is not row
                        or type(children.items) is not list):
                    raise ValueError("Неверная дочерняя коллекция поиска дерева")
                if children.items:
                    if len(pending) >= _MAX_DEPTH + 1:
                        raise ValueError("ДеревоЗначений: превышена глубина поиска Yadinassi")
                    pending.append((children, iter(children.items)))
        return None

    def find_rows(self, filters, recursive=False):
        """Native-backed scalar search; membership snapshot, shared live rows."""
        self._live()
        if type(filters) is not BSLStructure:
            raise TypeError("Ожидается Структура отбора")
        if len(filters._items) > _MAX_COLUMNS or len(self.tree.columns.items) > _MAX_COLUMNS:
            raise ValueError("ДеревоЗначений: превышен предел колонок поиска Yadinassi")
        budget = _SearchBudget()
        recursive = _search_recursive(recursive, budget)
        result = BSLArray()
        if not filters._items:
            return result

        # Resolve every field before any empty-receiver shortcut or cell scan.
        # This temporary schema map is not a row index; hierarchy determines order.
        columns = {_search_name(column.name, budget): column
                   for column in self.tree.columns.items}
        selected = []
        for name, value in filters._items.values():
            key = _search_name(name, budget)
            column = columns.get(key)
            if column is None:
                raise ValueError("Колонка поиска дерева не найдена")
            selected.append((column, value))
        prepared = [(column, value, _search_scalar(value, budget))
                    for column, value in selected]

        # Iterator frames, not recursion or the insertion-order _all_rows registry.
        pending = [(self, iter(self.items))]
        visited = cells = 0
        while pending:
            collection, iterator = pending[-1]
            try:
                row = next(iterator)
            except StopIteration:
                pending.pop()
                continue
            visited += 1
            cells += len(prepared)
            if visited > _MAX_ROWS or cells > _MAX_CELLS:
                raise ValueError("ДеревоЗначений: превышен предел ресурсов поиска Yadinassi")
            budget.charge(1)
            if type(row) is not BSLValueTreeRow or row.tree is not self.tree or row.collection is not collection:
                raise ValueError("Строка не принадлежит коллекции поиска дерева")
            row._live()
            if row.depth > _MAX_DEPTH:
                raise ValueError("ДеревоЗначений: превышена глубина поиска Yadinassi")
            values = []
            # Validate ALL selected cells before conjunction short-circuiting.
            # Charge both operands before equality, including repeated query text.
            for column, query, units in prepared:
                value = row.cells[column]
                _search_scalar(value, budget)
                budget.charge(units)
                values.append(value)
            if all(equal(value, query) for value, (_, query, _) in zip(values, prepared)):
                result.items.append(row)
            if recursive and row.rows.items:
                if len(pending) >= _MAX_DEPTH + 1:
                    raise ValueError("ДеревоЗначений: превышена глубина поиска Yadinassi")
                pending.append((row.rows, iter(row.rows.items)))
        return result

    def unload_column(self, column):
        """Local-row value snapshot; cells are shared, array membership is not."""
        self._live()
        columns = self.tree.columns.items
        if type(columns) is not list or type(self.items) is not list:
            raise ValueError("Неверная коллекция выгрузки дерева")
        if len(columns) > _MAX_COLUMNS or len(self.items) > _MAX_ROWS:
            raise ValueError("ДеревоЗначений: превышен предел выгрузки Yadinassi")
        budget = _SearchBudget()
        kind = type(column)
        if kind is str:
            key = _search_name(column, budget)
        elif kind is Decimal:
            _search_scalar(column, budget)  # Bound before numeric comparison/conversion.
            # Native 0.5/1.5/1.9/-0.5 witnesses select 0/1/1/0. This
            # method-local conversion does not change other tree index rules.
            integral = column.to_integral_value(rounding=ROUND_DOWN)
            if not 0 <= integral < len(columns):
                raise IndexError("Индекс колонки дерева вне границ")
            index = int(integral)  # Convert only after the bounded schema check.
        elif kind is not BSLValueTreeColumn:
            raise TypeError("ДеревоЗначений: неподдерживаемый селектор колонки")
        selected = None
        for position, candidate in enumerate(columns):
            if (type(candidate) is not BSLValueTreeColumn
                    or candidate.table is not self.tree or candidate._deleted):
                raise ValueError("Колонка не принадлежит дереву выгрузки")
            if kind is str:
                matches = _search_name(candidate.name, budget) == key
            elif kind is Decimal:
                matches = position == index
            else:
                matches = candidate is column
            if matches:
                selected = candidate
        # Resolve before empty-receiver shortcuts: unknown columns still fail.
        if selected is None:
            raise ValueError("Колонка выгрузки дерева не найдена")
        result = BSLArray()
        for row in self.items:
            if (type(row) is not BSLValueTreeRow or row.tree is not self.tree
                    or row.collection is not self):
                raise ValueError("Строка не принадлежит коллекции выгрузки дерева")
            row._live()
            if type(row.cells) is not dict:
                raise ValueError("Неверные ячейки строки выгрузки дерева")
            # Opaque references: no equality, copying, conversion or descendant walk.
            result.items.append(row.cells[selected])
        return result

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
            "find": self.find, "найти": self.find,
            "findrows": self.find_rows, "найтистроки": self.find_rows,
            "unloadcolumn": self.unload_column, "выгрузитьколонку": self.unload_column,
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
