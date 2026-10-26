"""Bounded ValueTable operations evidenced by collections.out's table checkpoint.

Budgets are Yadinassi limits, not native platform limits. Sort and GroupBy
use bounded native-backed helpers. Index definitions and exact-key lookup
maintenance follow the owner index checkpoint; unprobed foreign-row schemas
remain unsupported.
"""
from decimal import Decimal, InvalidOperation, localcontext

from .structures import BSLStructure, _key
from .type_descriptions import BSLTypeDescription, _number_value
from .type_qualifiers import BSLAllowedLength
from .values import (BSLArray, BSLFixedCollection, BSLObject, BSLType,
                     HostFunction, NULL, equal, number)

_MAX_CELLS = 1_000_000
_MAX_COLUMNS = 4096
_MAX_ROWS = 100_000
_MAX_TEXT = 1_000_000
_MAX_TOTAL_PRECISION = 16_384
_MAX_INDEXES = 256
_MAX_INDEX_COLUMNS = 4096
_MAX_INDEX_CELLS = 1_000_000
_MAX_INDEX_UNITS = 8_000_000
_MAX_INDEX_WORK = 8_000_000


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
    if BSLType.UUID in description.types:
        raise ValueError("Типизированные ячейки UUID пока не поддерживаются")
    if description.types == (BSLType.STRING,):
        q = description.string_qualifiers
        if q.allowed_length is BSLAllowedLength.FIXED:
            if q.length > _MAX_TEXT:
                raise ValueError("ТаблицаЗначений: превышен предел ресурсов Yadinassi")
            return " " * int(q.length)
    return description.adjust_value()


def _adjust(description, value):
    if BSLType.UUID in description.types:
        raise ValueError("Типизированные ячейки UUID пока не поддерживаются")
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


def _index_token(value):
    """Hashable typed equality tokens, without calling arbitrary host hooks.

    Keys retain their scalar values. Native object collections use identity;
    unknown host equality is deliberately not approximated by identity.
    """
    from .dates import BSLDate
    kind = type(value)
    if value is None or value is NULL or kind is bool or kind is BSLType:
        return kind, value
    if kind is str:
        return str, _text(value)
    if kind is Decimal:
        _number_value(value)
        if abs(value.adjusted()) > 4096:
            raise ValueError("Индексы: число вне ресурсных границ Yadinassi")
        return Decimal, value
    if kind is BSLDate:
        return BSLDate, value.require_known().ticks
    if kind is BSLTypeDescription:
        return BSLTypeDescription, value
    if issubclass(kind, BSLFixedCollection):
        return object, id(value)
    # These exact built-in types have identity equality. Avoid type equality,
    # arbitrary hash methods, and hostile metaclass attribute hooks.
    from .type_values import _VALUE_TYPES
    if any(kind is known for known, _, _ in _VALUE_TYPES):
        return object, id(value)
    raise ValueError("Индексы: тип ключа пока не поддерживается в Yadinassi")


def _index_key_units(key):
    # Conservative logical content, including repeated scalar references.
    return sum(len(value) if kind is str else len(value.as_tuple().digits)
               if kind is Decimal else 1 for kind, value in key)


class BSLCollectionIndex(BSLObject):
    """One ordered definition, with insertion-ordered buckets of live rows."""
    def __init__(self, table, columns):
        self.table = table
        self.columns = list(columns)
        self._deleted = False
        self._cleared = False
        self._buckets = {}
        self._keys = {}
        self._units = 0
        self._rebuild()

    def __str__(self):
        if self._cleared:
            raise ValueError("Индекс коллекции очищен")
        return ", ".join(self)

    def __iter__(self):
        return iter([column.name if column is not None else ""
                     for column in self.columns])

    def get_index(self, index):
        column = self.columns[_position(index, len(self.columns))]
        return column.name if column is not None else ""

    def set_index(self, index, value):
        raise ValueError("Индекс коллекции недоступен для изменения")

    def _key(self, row, changed=None, value=None):
        return tuple(_index_token(value if column is changed else row.cells[column])
                     for column in self.columns)

    def _append(self, row, key):
        if self.columns:
            self._keys[row] = key
            self._units += _index_key_units(key)
            self._buckets.setdefault(key, {})[row] = None

    def _remove(self, row):
        if row not in self._keys:
            return
        key = self._keys.pop(row)
        self._units -= _index_key_units(key)
        bucket = self._buckets.pop(key)
        del bucket[row]
        if bucket:
            # A bucket key always shares a live row's key representation.
            self._buckets[self._keys[next(iter(bucket))]] = bucket

    def _build(self, columns, other_units=0):
        # Build transactionally and bound content before hashing each key.
        buckets, keys, units = {}, {}, 0
        for row in self.table.rows if columns else ():
            key = tuple(_index_token(row.cells[column]) for column in columns)
            units += _index_key_units(key)
            if units + other_units > _MAX_INDEX_UNITS:
                raise ValueError("Индексы: превышен предел содержимого ключей Yadinassi")
            keys[row] = key
            buckets.setdefault(key, {})[row] = None
        return buckets, keys, units

    def _rebuild(self):
        other_units = sum(index._units for index in self.table.indexes.items if index is not self)
        self._buckets, self._keys, self._units = self._build(self.columns, other_units)


class BSLCollectionIndexes(BSLObject):
    def __init__(self, table):
        self.table = table
        self.items = []

    def __str__(self):
        return "ИндексыКоллекции"

    def __iter__(self):
        return iter(self.items)

    def get_index(self, index):
        return self.items[_position(index, len(self.items))]

    def set_index(self, index, value):
        raise ValueError("Индексы коллекции недоступны для замены")

    def _check_units(self, delta):
        if sum(index._units for index in self.items) + delta > _MAX_INDEX_UNITS:
            raise ValueError("Индексы: превышен предел содержимого ключей Yadinassi")

    def _budget(self, rows=None, extra_columns=None):
        rows = len(self.table.rows) if rows is None else rows
        columns = sum(max(1, len(index.columns)) for index in self.items)
        count = len(self.items)
        if extra_columns is not None:
            count += 1
            columns += max(1, len(extra_columns))
        if (count > _MAX_INDEXES or columns > _MAX_INDEX_COLUMNS
                or rows * columns > _MAX_INDEX_CELLS):
            raise ValueError("Индексы: превышен предел ресурсов Yadinassi")

    def _add_columns(self, columns):
        # Internal codec/copy entry point; schema references, never guessed names.
        if any(type(column) is not BSLValueTableColumn or column.table is not self.table
               or column._deleted or column not in self.table.columns.items
               for column in columns):
            raise ValueError("Индекс: колонка не принадлежит таблице")
        self._budget(extra_columns=columns)
        index = BSLCollectionIndex(self.table, columns)
        self.items.append(index)
        return index

    def add(self, columns=None):
        if columns is None:
            return self._add_columns([])
        columns = _text(columns)
        if columns.count(",") + 1 > _MAX_INDEX_COLUMNS:
            raise ValueError("Индексы: превышен предел списка колонок Yadinassi")
        by_name = {column.name.casefold(): column for column in self.table.columns.items}
        selected = []
        for part in columns.split(","):
            name = part.strip()
            if not name:
                continue
            column = by_name.get(name.casefold())
            if column is None:
                raise ValueError(f"Колонка не найдена: {name}")
            selected.append(column)
        return self._add_columns(selected)

    def delete(self, index):
        if type(index) is not BSLCollectionIndex:
            if type(index) is str:
                _text(index)
                if len(index) > 4096:
                    raise ValueError("Индексы: превышен предел числа Yadinassi")
                with localcontext():
                    try:
                        index = number(index)
                    except InvalidOperation as error:
                        raise ValueError("Индекс: ожидается число") from error
            index = self.get_index(index)
        if index.table is not self.table or index._deleted or index not in self.items:
            raise ValueError("Индекс не принадлежит коллекции")
        self.items.remove(index)
        index._deleted = True
        index._buckets.clear()
        index._keys.clear()
        index._units = 0

    def clear(self):
        for index in self.items:
            index._deleted = True
            index._cleared = True
            index.columns[:] = [None] * len(index.columns)
            index._buckets.clear()
            index._keys.clear()
            index._units = 0
        self.items.clear()

    def _column_deleted(self, column):
        plans = []
        delta = 0
        for index in self.items:
            if column in index.columns:
                columns = [item for item in index.columns if item is not column]
                state = index._build(columns)
                plans.append((index, columns, state))
                delta += state[2] - index._units
        self._check_units(delta)
        for index, columns, state in plans:
            index.columns[:] = columns
            index._buckets, index._keys, index._units = state

    def _row_added(self, row):
        keys = [(index, index._key(row)) for index in self.items if index.columns]
        self._check_units(sum(_index_key_units(key) for _, key in keys))
        for index, key in keys:
            index._append(row, key)

    def _row_deleted(self, row):
        for index in self.items:
            index._remove(row)

    def _rows_cleared(self):
        for index in self.items:
            index._buckets.clear()
            index._keys.clear()
            index._units = 0

    def _rows_reordered(self):
        # Sort and Move reset native lookup order to physical table order.
        # Keys and their bounded content are unchanged; never re-tokenize them.
        for index in self.items:
            buckets = {}
            for row in self.table.rows if index.columns else ():
                buckets.setdefault(index._keys[row], {})[row] = None
            index._buckets = buckets

    def _check_bulk_work(self, rows, columns):
        widths = {}
        for index in self.items:
            for column in set(index.columns):
                widths[column] = widths.get(column, 0) + len(index.columns)
        # Repeated selected columns cause repeated writes and are counted.
        work = rows * sum(1 + widths.get(column, 0) for column in columns)
        if work > _MAX_INDEX_WORK:
            raise ValueError("Индексы: превышен предел работы изменения Yadinassi")
        return work

    def _prepare_fill(self, value, columns):
        rows = self.table.rows
        work = self._check_bulk_work(len(rows), columns)
        if not rows or not self.items:
            return {}
        counts = {}
        for column in columns:
            counts[column] = counts.get(column, 0) + 1
        weights, growth = {}, {}
        for index in self.items:
            changes = sum(counts.get(column, 0) for column in set(index.columns))
            work += index._units * changes
            for column in index.columns:
                if column in counts:
                    weights[column] = weights.get(column, 0) + 1
                    growth[column] = growth.get(column, 0) + changes
        if work > _MAX_INDEX_WORK:
            raise ValueError("Индексы: превышен предел работы изменения Yadinassi")
        units = sum(index._units for index in self.items)
        prepared = {}
        for column in columns:
            if column in prepared or column not in weights:
                continue
            adjusted = _adjust(column.value_type, value)
            new_units = _index_key_units((_index_token(adjusted),))
            # Bound every revisit of earlier replacement values, conservatively.
            work += len(rows) * new_units * growth[column]
            if work > _MAX_INDEX_WORK:
                raise ValueError("Индексы: превышен предел работы изменения Yadinassi")
            for row in rows:
                old_units = _index_key_units((_index_token(row.cells[column]),))
                units += weights[column] * (new_units - old_units)
                if units > _MAX_INDEX_UNITS:
                    raise ValueError("Индексы: превышен предел содержимого ключей Yadinassi")
            prepared[column] = adjusted
        return prepared

    def _prepare_load(self, values, column):
        rows = self.table.rows[:len(values)]
        work = self._check_bulk_work(len(rows), [column])
        affected = [(index, index.columns.count(column))
                    for index in self.items if column in index.columns]
        if not affected:
            return None
        weight = sum(count for _, count in affected)
        units = sum(index._units for index in self.items)
        prepared = []
        for row, value in zip(rows, values):
            adjusted = _adjust(column.value_type, value)
            new_units = _index_key_units((_index_token(adjusted),))
            old_units = _index_key_units((_index_token(row.cells[column]),))
            work += sum(_index_key_units(index._keys[row]) for index, _ in affected)
            work += weight * new_units
            if work > _MAX_INDEX_WORK:
                raise ValueError("Индексы: превышен предел работы изменения Yadinassi")
            units += weight * (new_units - old_units)
            if units > _MAX_INDEX_UNITS:
                raise ValueError("Индексы: превышен предел содержимого ключей Yadinassi")
            prepared.append(adjusted)
        return prepared

    def _set_cell(self, row, column, value):
        keys = [(index, index._key(row, column, value))
                for index in self.items if column in index.columns]
        self._check_units(sum(_index_key_units(key) - _index_key_units(index._keys[row])
                              for index, key in keys))
        row.cells[column] = value
        for index, key in keys:
            # Native also reinserts an equality-preserving write to an indexed
            # field, while a write to an unrelated column leaves order alone.
            index._remove(row)
            index._append(row, key)

    def _lookup(self, selected):
        # Only complete exact-column keys are established by the checkpoint.
        # Filter property order is irrelevant; index definition order is not.
        columns = {column for column, _ in selected}
        values = dict(selected)
        candidates = []
        for index in self.items:
            if index.columns and set(index.columns) == columns:
                key = tuple(_index_token(values[column]) for column in index.columns)
                if _index_key_units(key) > _MAX_INDEX_UNITS:
                    raise ValueError("Индексы: превышен предел содержимого ключей Yadinassi")
                duplicate = len(index.columns) != len(columns)
                candidates.append((index._buckets.get(key, {}), duplicate))
        if not candidates:
            return None
        if any(duplicate for _, duplicate in candidates):
            # Repeated fields are confirmed metadata, but optimizer selection is
            # not. Permit only results invariant between duplicate-field lookup
            # and an ordinary exact index (or the table scan when none exists).
            ordinary = next((bucket for bucket, duplicate in candidates if not duplicate), None)
            matching = {id(row) for row in candidates[0][0]}
            expected = (list(ordinary) if ordinary is not None else
                        [row for row in self.table.rows if id(row) in matching])
            for bucket, duplicate in candidates:
                if duplicate and (len(bucket) != len(expected) or
                                  any(left is not right for left, right in zip(bucket, expected))):
                    raise ValueError("Поиск: порядок индекса с повторными колонками пока не подтвержден")
        return candidates[0][0]

    def get_method(self, name):
        return _method(name, {
            "count": lambda: Decimal(len(self.items)), "количество": lambda: Decimal(len(self.items)),
            "add": self.add, "добавить": self.add, "delete": self.delete, "удалить": self.delete,
            "clear": self.clear, "очистить": self.clear})


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
        self.table.indexes._column_deleted(column)
        self.items.remove(column)
        for row in self.table.rows:
            del row.cells[column]
        column._deleted = True
        column.name, column.title, column.width = "", "", Decimal(0)
        column.value_type = BSLTypeDescription()
        if not self.items:
            self.table.clear()

    def clear(self):
        # Drop all references once; repeated per-column rebuilds are quadratic.
        for index in self.table.indexes.items:
            index.columns.clear()
        self.table.indexes._rows_cleared()
        for column in list(self.items):
            self.delete(column)
        self.table.clear()

    def move(self, column, offset):
        if not (type(column) is Decimal or type(column) is str
                or type(column) is BSLValueTableColumn):
            raise TypeError("Ожидается имя, индекс или колонка таблицы")
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
        self.table.indexes._set_cell(self, column, _adjust(column.value_type, value))

    def get_index(self, index):
        self._live()
        return self.cells[self.table.columns.get_index(index)]

    def set_index(self, index, value):
        self._live()
        column = self.table.columns.get_index(index)
        self.table.indexes._set_cell(self, column, _adjust(column.value_type, value))

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
        self.indexes = BSLCollectionIndexes(self)

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
        if self.indexes.items and position != len(self.rows):
            raise ValueError("Вставка не в конец таблицы с индексами пока не подтверждена")
        self._budget(len(self.rows) + 1, len(self.columns.items))
        self.indexes._budget(rows=len(self.rows) + 1)
        row = BSLValueTableRow(self)
        self.indexes._row_added(row)
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
        self.indexes._row_deleted(row)
        row._deleted = True
        row.cells.clear()

    def clear(self):
        self.indexes._rows_cleared()
        for row in self.rows:
            row._deleted = True
            row.cells.clear()
        self.rows.clear()

    def move(self, row, offset):
        row = self._resolve_row(row)
        old = self.rows.index(row)
        new = _position(Decimal(old + _integer(offset)), len(self.rows))
        self.rows.insert(new, self.rows.pop(old))
        self.indexes._rows_reordered()

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
        if (columns is None or columns == "") and self.indexes.items:
            # An implicit all-column search is established only where scan and
            # plausible single-column index choices return the same row.
            physical = next((row for row in self.rows
                             if any(equal(row.cells[column], value) for column in selected)), None)
            checked = set()
            for index in self.indexes.items:
                if not index.columns or index.columns[0] in checked:
                    continue
                column = index.columns[0]
                if any(other is not column for other in index.columns):
                    continue
                checked.add(column)
                candidates = self.indexes._lookup([(column, value)])
                indexed = next(iter(candidates), None)
                if indexed is not None and indexed is not physical:
                    raise ValueError("Поиск без списка колонок при различном порядке индекса пока не подтвержден")
            return physical
        candidates = self.indexes._lookup([(selected[0], value)]) if len(selected) == 1 else None
        source = self.rows if candidates is None else candidates
        return next((r for r in source if any(equal(r.cells[c], value) for c in selected)), None)

    def find_rows(self, filters):
        if type(filters) is not BSLStructure:
            raise TypeError("Ожидается Структура отбора")
        if not filters._items:
            return _array([])
        selected = [(self.columns.get_index(name), value) for name, value in filters._items.values()]
        candidates = self.indexes._lookup(selected)
        source = self.rows if candidates is None else candidates
        return _array(r for r in source if all(equal(r.cells[c], v) for c, v in selected))

    def fill_values(self, value, columns=None):
        selected = self._selection(columns)  # Native validates names before mutation.
        prepared = self.indexes._prepare_fill(value, selected)
        for column in selected:
            adjusted = prepared[column] if column in prepared else _adjust(column.value_type, value)
            for row in self.rows:
                self.indexes._set_cell(row, column, adjusted)

    def load_column(self, values, column):
        if type(values) is not BSLArray:
            raise TypeError("Ожидается Массив")
        column = self.columns.resolve(column)
        prepared = self.indexes._prepare_load(values.items, column)
        source = values.items if prepared is None else prepared
        for row, value in zip(self.rows, source):
            adjusted = _adjust(column.value_type, value) if prepared is None else value
            self.indexes._set_cell(row, column, adjusted)

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
        result = sort_table(self, columns, comparator)
        self.indexes._rows_reordered()
        return result

    def group_by(self, grouping_columns, totaling_columns=None):
        from .value_table_group import group_by
        return group_by(self, grouping_columns, totaling_columns)

    def copy_columns(self, columns=None):
        result = BSLValueTable()
        for column in self._selection(columns):
            result.columns.add(column.name, column.value_type, column.title, column.width)
        return result

    def copy(self, rows=None, columns=None):
        if type(columns) is str and columns == "" and self.indexes.items:
            raise ValueError("Копирование таблицы с индексами и пустым списком колонок пока не подтверждено")
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
        if columns is None or columns == "":
            mapping = dict(zip(selected, result.columns.items))
            for index in self.indexes.items:
                result.indexes._add_columns([mapping[column] for column in index.columns])
        return result

    def get_member(self, name):
        if name.casefold() in ("indexes", "индексы"):
            return self.indexes
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
