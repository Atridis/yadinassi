"""Bounded catalog tabular-section buffers; native parity is not yet measured.

Row UUIDs are internal backend identities, never BSL references or line numbers.
Only the owning CatalogObject.Write persists these detached buffers.
"""
from decimal import Decimal
from uuid import UUID, uuid4

from .catalog_backend import BackendError, TabularRow, TabularSectionRows
from .catalog_types import BSLCatalogReference
from .dates import BSLDate
from .values import BSLObject, HostFunction

_MAX_ROWS = 1000
_MAX_BUFFER_BYTES = 4 * 1024 * 1024


def _index(value, count):
    if type(value) is not Decimal or not value.is_finite():
        raise TypeError('tabular section index requires a finite Number')
    if value < 0 or value >= count:
        raise IndexError('tabular section index out of bounds')
    result = int(value)
    if value != result:
        raise ValueError('fractional tabular section index is unsupported')
    return result


def _units(value):
    if type(value) is str:
        if len(value) > 65536: raise ValueError('tabular field text limit')
        return len(value.encode('utf-8'))
    if type(value) is Decimal:
        # Bound the coefficient before as_tuple materializes it. Do not format
        # fixed-point text here: an unbounded exponent could expand enormously.
        if value.__sizeof__() > 2048: raise ValueError('tabular field number limit')
        parts = value.as_tuple()
        return len(parts.digits) + len(str(parts.exponent)) + 3
    if type(value) is bool: return 1
    if type(value) is BSLDate: return 14
    if type(value) is BSLCatalogReference: return 36
    raise TypeError('unsupported tabular field value')


class BSLCatalogSectionRow(BSLObject):
    def __init__(self, section, identity, values):
        self._section = section
        self._identity = identity
        self._values = dict(values)
        self._attached = True
        self._bytes = 52 + sum(_units(value) for value in self._values.values())

    def _require(self, mutate=False):
        if not self._attached: raise ValueError('detached tabular row is unavailable')
        if mutate: self._section._mutable()

    def get_member(self, name):
        self._require()
        if type(name) is not str: raise TypeError('tabular field name requires String')
        key = name.casefold()
        if key not in self._values: return super().get_member(name)
        return self._values[key]

    def set_member(self, name, value):
        self._require(True)
        if type(name) is not str: raise TypeError('tabular field name requires String')
        key = name.casefold()
        field = self._section._fields.get(key)
        if field is None: raise ValueError('tabular field not found')
        value = self._section._owner._manager._assigned(field, value)
        delta = _units(value) - _units(self._values[key])
        if self._section._owner._section_buffer_bytes() + delta > _MAX_BUFFER_BYTES:
            raise ValueError('tabular section buffer limit')
        self._values[key] = value
        self._bytes += delta
        self._section._bytes += delta
        self._section._dirty = True

    def get_index(self, name): return self.get_member(name)
    def set_index(self, name, value): self.set_member(name, value)
    def __str__(self): raise ValueError('tabular row presentation is unsupported')


class BSLCatalogSection(BSLObject):
    def __init__(self, owner, schema, rows=()):
        self._owner, self._schema = owner, schema
        self._fields = {f.name.casefold(): f for f in schema.fields}
        if len(self._fields) != len(schema.fields) or {'linenumber', 'номерстроки'} & self._fields.keys():
            raise BackendError('unsupported')
        self._rows = []; self._version = 0; self._dirty = False; self._bytes = 0
        if type(rows) is not tuple or len(rows) > _MAX_ROWS: raise BackendError('integrity')
        seen = set()
        for row in rows:
            if (type(row) is not TabularRow or type(row.identity) is not UUID or not row.identity.int
                    or row.identity in seen or type(row.values) is not tuple or len(row.values) != len(schema.fields)):
                raise BackendError('integrity')
            seen.add(row.identity)
            values = {f.name.casefold(): owner._manager._logical(f, v) for f, v in zip(schema.fields, row.values)}
            loaded = BSLCatalogSectionRow(self, row.identity, values)
            self._rows.append(loaded); self._bytes += loaded._bytes
            if self._bytes > _MAX_BUFFER_BYTES: raise BackendError('unsupported')

    def _mutable(self):
        if self._owner._pending_write is not None: raise BackendError('uncertain_commit')
        if not self._owner._manager._backend.capabilities().catalog_tabular_sections:
            raise BackendError('unsupported')

    def count(self): return Decimal(len(self._rows))
    def get(self, index): return self._rows[_index(index, len(self._rows))]
    def get_index(self, index): return self.get(index)
    def set_index(self, index, value):
        self._mutable()
        raise ValueError('tabular row replacement is unsupported')

    def add(self):
        self._mutable()
        if self._owner._section_row_count() >= _MAX_ROWS:
            raise ValueError('tabular section row limit')
        values = {f.name.casefold(): self._owner._manager._field_default(f) for f in self._schema.fields}
        row = BSLCatalogSectionRow(self, uuid4(), values)
        if self._owner._section_buffer_bytes() + row._bytes > _MAX_BUFFER_BYTES:
            raise ValueError('tabular section buffer limit')
        self._rows.append(row); self._bytes += row._bytes
        self._version += 1; self._dirty = True
        return row

    def clear(self):
        self._mutable()
        for row in self._rows: row._attached = False
        self._rows.clear(); self._bytes = 0
        self._version += 1; self._dirty = True

    def delete(self, value):
        self._mutable()
        if type(value) is BSLCatalogSectionRow:
            if value._section is not self or not value._attached:
                raise ValueError('tabular row belongs to another section or is detached')
            index = self._rows.index(value)
        else:
            index = _index(value, len(self._rows))
        row = self._rows.pop(index)
        row._attached = False; self._bytes -= row._bytes
        self._version += 1; self._dirty = True

    def __iter__(self):
        version = self._version
        def iterate():
            position = 0
            while True:
                if version != self._version:
                    raise ValueError('tabular collection changed during iteration')
                if position == len(self._rows): return
                row = self._rows[position]
                position += 1
                yield row
        return iterate()

    def _stored_rows(self):
        manager = self._owner._manager
        return TabularSectionRows(self._schema.identity, tuple(TabularRow(row._identity,
            tuple(manager._stored(f, row._values[f.name.casefold()]) for f in self._schema.fields)) for row in self._rows))

    def get_member(self, name):
        methods = {'add': self.add, 'добавить': self.add, 'count': self.count, 'количество': self.count,
                   'get': self.get, 'получить': self.get, 'clear': self.clear, 'очистить': self.clear,
                   'delete': self.delete, 'удалить': self.delete}
        method = methods.get(name.casefold())
        return HostFunction(name, method) if method else super().get_member(name)

    def __str__(self): raise ValueError('tabular section presentation is unsupported')
