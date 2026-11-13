"""Fixed host-registered form tables, not native parity or ValueTable schemas.

Only scalar cells participate in the private form-state protocol. Live owned
collections/rows have no public constructor, persistence or Invocation codec.
All limits here are host budgets, not claims about native 1C maxima.
"""
from dataclasses import dataclass
from decimal import Decimal
import json

from .file_io import _methods
from .form_model import BSLFormAttribute, _Owned, name, scalar, text, MAX_TOTAL_TEXT
from .form_references import is_reference, adjust, encode, require_scope
from .values import BSLType

MAX_TABLES = 4
MAX_TABLE_COLUMNS = 8
MAX_TABLE_ROWS = 32
MAX_TABLE_CELLS = 256
MAX_TABLE_ALLOCATED = 4096
MAX_TABLE_DATA_BYTES = 32768
_TYPE_NAMES = {BSLType.STRING: 'String', BSLType.NUMBER: 'Number',
               BSLType.BOOLEAN: 'Boolean', BSLType.DATE: 'Date'}


@dataclass(frozen=True)
class FormTableColumn:
    name: str
    value_type: object
    title: str = ''
    read_only: bool = False

    def __post_init__(self):
        BSLFormAttribute(self.name, self.value_type, title=self.title)
        if type(self.read_only) is not bool:
            raise TypeError('ТаблицаФормы: ожидается Булево')
        if self.name.casefold() in ('getid', 'получитьидентификатор'):
            raise ValueError('ТаблицаФормы: имя колонки занято')


@dataclass(frozen=True)
class FormTableSchema:
    name: str
    columns: tuple
    title: str = ''

    def __post_init__(self):
        name(self.name); text(self.title, 1024)
        if (type(self.columns) is not tuple or
                not 1 <= len(self.columns) <= MAX_TABLE_COLUMNS or
                any(type(column) is not FormTableColumn for column in self.columns)):
            raise ValueError('ТаблицаФормы: неверная схема колонок')
        keys = [column.name.casefold() for column in self.columns]
        if len(keys) != len(set(keys)):
            raise ValueError('ТаблицаФормы: повторная колонка')


@dataclass(frozen=True)
class FormTableSnapshot:
    identity: int
    name: str
    title: str
    columns: tuple
    rows: tuple
    allocated: int


def _row_identity(value):
    if type(value) is not int or not 1 <= value <= MAX_TABLE_ALLOCATED:
        raise ValueError('ТаблицаФормы: неверный идентификатор строки')
    return value


def _position(value, count):
    if (type(value) is not Decimal or not value.is_finite() or
            value != value.to_integral_value() or not 0 <= value < count):
        raise ValueError('ТаблицаФормы: индекс вне границ')
    return int(value)


def table_text_size(form):
    return sum(len(value) for table in form._tables.values()
               for row in table._rows for value in row._data.values()
               if type(value) is str)


def _validate_rows(table, rows):
    # Keep ordinary Interpreter/type-registry imports free of the opt-in UI.
    from .ui.protocol import encode_value
    if type(rows) is not tuple or len(rows) > MAX_TABLE_ROWS:
        raise ValueError('ТаблицаФормы: превышен предел строк')
    identities = set(); encoded_rows = []; total_text = 0
    for record in rows:
        if type(record) is not tuple or len(record) != 2:
            raise ValueError('ТаблицаФормы: неверная строка')
        identity, values = record
        _row_identity(identity)
        if identity in identities:
            raise ValueError('ТаблицаФормы: повторная строка')
        identities.add(identity)
        if type(values) is not tuple or len(values) != len(table.schema.columns):
            raise ValueError('ТаблицаФормы: неверные ячейки')
        encoded = []
        for column, value in zip(table.schema.columns, values):
            tagged = encode(column.value_type, value, encode_value)
            if encode(column.value_type, adjust(column.value_type, value), encode_value) != tagged:
                raise ValueError('ТаблицаФормы: значение вне схемы')
            encoded.append(tagged)
            if type(value) is str: total_text += len(value)
        encoded_rows.append([identity, encoded])
    return encoded_rows, total_text


def validate_table_data(form, replacements=None, scalar_data=None):
    """Validate a detached final candidate before any live rows are changed.

    replacements maps registered casefold names to immutable (id, values) rows.
    The 32 KiB bound covers the compact UTF-8 tagged cell data of all tables,
    including table and row IDs. Frame/schema overhead has a separate host cap.
    """
    if replacements is None: replacements = {}
    if type(replacements) is not dict or not set(replacements) <= set(form._tables):
        raise ValueError('ТаблицаФормы: неизвестная таблица')
    if len(form._tables) > MAX_TABLES:
        raise ValueError('ТаблицаФормы: превышен предел таблиц')
    data = form._data if scalar_data is None else scalar_data
    total_text = sum(len(value) for value in data.values() if type(value) is str)
    cells = 0; packet = []
    for key, table in form._tables.items():
        rows = replacements.get(key, table._snapshot().rows)
        encoded_rows, row_text = _validate_rows(table, rows)
        cells += len(rows) * len(table.schema.columns)
        total_text += row_text
        packet.append([table._identity, encoded_rows])
    if cells > MAX_TABLE_CELLS or total_text > MAX_TOTAL_TEXT:
        raise ValueError('ТаблицаФормы: превышен предел данных')
    if len(json.dumps(packet, ensure_ascii=False, separators=(',', ':'),
                      allow_nan=False).encode('utf-8')) > MAX_TABLE_DATA_BYTES:
        raise ValueError('ТаблицаФормы: превышен предел передаваемых данных')


class BSLFormDataCollection(_Owned):
    _methods = _methods(('add', True, 'Add Добавить'), ('get', True, 'Get Получить'),
                        ('count', True, 'Count Количество'),
                        ('delete', False, 'Delete Удалить'), ('clear', False, 'Clear Очистить'))

    def __init__(self, form, schema, identity):
        super().__init__(form)
        if type(schema) is not FormTableSchema or type(identity) is not int or not 1 <= identity <= MAX_TABLES:
            raise ValueError('ТаблицаФормы: неверная регистрация')
        for column in schema.columns: require_scope(column.value_type, form._session)
        self.schema, self._identity = schema, identity
        self._rows = []; self._by_id = {}; self._allocated = 0

    def _check(self, server=False):
        super()._check(server)
        if self._form._tables.get(self.schema.name.casefold()) is not self:
            raise ValueError('ТаблицаФормы: чужая или отсоединенная коллекция')

    def _lookup_id(self, identity):
        _row_identity(identity)
        row = self._by_id.get(identity)
        if row is None or row._removed or row._table is not self:
            raise ValueError('ТаблицаФормы: строка не найдена')
        return row

    def _snapshot(self):
        columns = tuple((c.name, c.title, c.value_type.scope.wire_type(c.value_type.target) if is_reference(c.value_type) else _TYPE_NAMES[c.value_type.types[0]], c.read_only)
                        for c in self.schema.columns)
        rows = tuple((r._row_id, tuple(r._data[c.name.casefold()] for c in self.schema.columns))
                     for r in self._rows)
        return FormTableSnapshot(self._identity, self.schema.name, self.schema.title,
                                 columns, rows, self._allocated)

    def _replace_rows(self, rows, allocated):
        """Trusted replica install after aggregate validation of the final state.

        Checks local shape/value/identity invariants, not intermediate aggregate
        budgets: several tables may shrink/grow atomically in one response.
        """
        if type(allocated) is not int or not self._allocated <= allocated <= MAX_TABLE_ALLOCATED:
            raise ValueError('ТаблицаФормы: неверный счетчик строк')
        _validate_rows(self, rows)
        for identity, values in rows:
            if identity > allocated or identity not in self._by_id and identity <= self._allocated:
                raise ValueError('ТаблицаФормы: повторное использование строки')
        result = []
        for identity, values in rows:
            row = self._by_id.get(identity)
            if row is None: row = BSLFormDataCollectionItem(self, identity)
            row._data = {column.name.casefold(): value
                         for column, value in zip(self.schema.columns, values)}
            result.append(row)
        retained = {row._row_id for row in result}
        for row in self._rows:
            if row._row_id not in retained: row._removed = True
        self._rows = result; self._by_id = {row._row_id: row for row in result}
        self._allocated = allocated
        self._clear_removed_selection()

    def _clear_removed_selection(self):
        from .form_model import BSLFormTable
        for item in self._form.items._values.values():
            if (type(item) is BSLFormTable and item.data_path.casefold() == self.schema.name.casefold()
                    and item.current_row is not None and item.current_row not in self._by_id):
                item.current_row = None

    def add(self):
        self._check(True)
        if self._allocated >= MAX_TABLE_ALLOCATED or len(self._rows) >= MAX_TABLE_ROWS:
            raise ValueError('ТаблицаФормы: превышен предел строк')
        identity = self._allocated + 1
        values = tuple(adjust(c.value_type) for c in self.schema.columns)
        rows = self._snapshot().rows + ((identity, values),)
        validate_table_data(self._form, {self.schema.name.casefold(): rows})
        self._replace_rows(rows, identity)
        return self._by_id[identity]

    def get(self, index):
        self._check(); return self._rows[_position(index, len(self._rows))]

    def get_index(self, index): return self.get(index)

    def set_index(self, index, value):
        self._check(); raise ValueError('ТаблицаФормы: замена строки запрещена')

    def count(self): self._check(); return Decimal(len(self._rows))

    def delete(self, row):
        self._check(True)
        if type(row) is Decimal: row = self.get(row)
        if (type(row) is not BSLFormDataCollectionItem or row._table is not self or
                self._by_id.get(row._row_id) is not row or row._removed):
            raise ValueError('ТаблицаФормы: чужая или удаленная строка')
        self._replace_rows(tuple(record for record in self._snapshot().rows if record[0] != row._row_id), self._allocated)

    def clear(self):
        self._check(True); self._replace_rows((), self._allocated)

    def __iter__(self):
        self._check()
        # Snapshot membership, but every yielded handle is still ownership-checked.
        for row in tuple(self._rows):
            row._check(); yield row


class BSLFormDataCollectionItem(_Owned):
    _methods = _methods(('get_id', True, 'GetID ПолучитьИдентификатор'))

    def __init__(self, table, identity):
        super().__init__(table._form)
        self._table, self._row_id, self._data = table, _row_identity(identity), {}

    def _check(self, server=False):
        self._table._check(server)
        if self._removed or self._table._by_id.get(self._row_id) is not self:
            raise ValueError('ТаблицаФормы: чужая или удаленная строка')

    def get_id(self): self._check(); return Decimal(self._row_id)

    def get_member(self, member):
        self._check()
        key = member.casefold()
        if key in self._data: return self._data[key]
        return super().get_member(member)

    def set_member(self, member, value):
        self._check(); key = member.casefold()
        column = next((c for c in self._table.schema.columns if c.name.casefold() == key), None)
        if column is None: return super().set_member(member, value)
        if is_reference(column.value_type) and not column.value_type.scope.server:
            raise ValueError("client reference cells are read-only")
        value = adjust(column.value_type, value)
        rows = tuple((r._row_id, tuple(value if r is self and c.name.casefold() == key
                    else r._data[c.name.casefold()] for c in self._table.schema.columns))
                    for r in self._table._rows)
        validate_table_data(self._form, {self._table.schema.name.casefold(): rows})
        self._data[key] = value
