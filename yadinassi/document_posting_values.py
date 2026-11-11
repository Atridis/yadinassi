"""Closed posting modes and recorder-owned scalar buffers.

The detached buffer deliberately starts empty on object reload. Only the
same-object lifetime is established by the measured posting profile.
"""
from decimal import Decimal
from enum import Enum
from .values import BSLObject, HostFunction
from .catalog_backend import BackendError
from .document_movements import MAX_MOVEMENT_ROWS, RecorderMovementRow, RecorderReplacement
from .transaction_backend import TransactionRequest


class DocumentWriteMode(Enum):
    WRITE = 'write'
    POSTING = 'posting'
    UNDO_POSTING = 'undo_posting'
    def __str__(self): raise ValueError('document write mode presentation is outside this profile')


class _DocumentWriteModes(BSLObject):
    def __str__(self): raise ValueError('document write mode namespace presentation is unsupported')
    def get_member(self, name):
        values = {'write': DocumentWriteMode.WRITE, 'запись': DocumentWriteMode.WRITE,
                  'posting': DocumentWriteMode.POSTING, 'проведение': DocumentWriteMode.POSTING,
                  'undoposting': DocumentWriteMode.UNDO_POSTING, 'отменапроведения': DocumentWriteMode.UNDO_POSTING}
        if name.casefold() in values: return values[name.casefold()]
        return super().get_member(name)


DOCUMENT_WRITE_MODES = _DocumentWriteModes()
MAX_BUFFER_BYTES = 16 * 1024 * 1024


def _value_bytes(value):
    return len(value.encode('utf-8')) if type(value) is str else 32


class BSLRecorderRow(BSLObject):
    def __str__(self): raise ValueError('movement row presentation is unsupported')
    def __init__(self, owner):
        self._owner = owner
        self._active = True
        self._values = {field.name.casefold(): owner._document._manager._field_default(field)
                        for field in owner._schema.fields}
        self._bytes = 32 + sum(_value_bytes(value) for value in self._values.values())
    def _check(self):
        if not any(row is self for row in self._owner._rows): raise ValueError('detached movement row')
    def get_member(self, name):
        self._check(); key = name.casefold()
        if key in ('active','активность'): return self._active
        if key in ('linenumber','номерстроки'): return Decimal(self._owner._rows.index(self)+1)
        if key in ('recorder','регистратор'): return self._owner._document._manager._ref(self._owner._document._key.record_id)
        if key not in self._values: raise ValueError('movement field not found')
        return self._values[key]
    def set_member(self, name, value):
        self._check(); self._owner._mutable(); key = name.casefold()
        if key in ('active','активность'):
            if type(value) is not bool: raise TypeError('Active requires Boolean')
            self._active = value; return
        field = next((f for f in self._owner._schema.fields if f.name.casefold()==key),None)
        if field is None: raise ValueError('movement field is missing or read-only')
        value = self._owner._document._manager._assigned(field,value)
        delta = _value_bytes(value)-_value_bytes(self._values[key])
        self._owner._budget(delta)
        self._values[key] = value
        self._bytes += delta; self._owner._bytes += delta


class BSLRecorderSet(BSLObject):
    def __str__(self): raise ValueError('movement set presentation is unsupported')
    def __init__(self, document, schema):
        self._document, self._schema = document, schema
        self._rows = []; self._selected = False; self._bytes = 0
    def _mutable(self):
        if self._document._pending_write is not None and self._document._posting_active is None:
            raise BackendError('uncertain_commit')
        if not self._document._manager._writable(): raise BackendError('unsupported')
    def _budget(self, delta=0, added_rows=0):
        sets = self._document._movements._sets.values()
        if sum(len(item._rows) for item in sets)+added_rows > MAX_MOVEMENT_ROWS: raise BackendError('unsupported')
        if sum(item._bytes for item in self._document._movements._sets.values())+delta > MAX_BUFFER_BYTES: raise BackendError('unsupported')
    def add(self):
        self._mutable()
        row = BSLRecorderRow(self); self._budget(row._bytes,1)
        self._rows.append(row); self._bytes += row._bytes; return row
    def clear(self):
        self._mutable(); self._rows = []; self._bytes = 0
    def count(self): return Decimal(len(self._rows))
    def get(self, index):
        if type(index) is not Decimal or index != int(index): raise TypeError('movement index requires integer Number')
        if not 0 <= index < len(self._rows): raise ValueError('movement index out of range')
        return self._rows[int(index)]
    def _stored_rows(self):
        manager = self._document._manager
        return tuple(RecorderMovementRow(index,row._active,
                     tuple(manager._stored(field,row._values[field.name.casefold()]) for field in self._schema.fields))
                     for index,row in enumerate(self._rows,1))
    def _replace(self, transaction, rows):
        transaction._open()
        key = self._document._key
        snapshot = transaction.unit.read_recorder(self._schema.identity,key).snapshot
        transaction.unit.stage(TransactionRequest('recorder_replace',
            RecorderReplacement(self._schema.identity,key,rows,snapshot)))
    def write(self):
        transaction = self._document._posting_active
        if transaction is None: raise BackendError('unsupported')
        self._replace(transaction,self._stored_rows())
    def get_method(self, name):
        if name.casefold() in ('write','записать'): return HostFunction(name,self.write,returns_value=False)
        return super().get_method(name)
    def get_member(self, name):
        key = name.casefold()
        if key in ('write','записывать'): return self._selected
        methods = {'add':self.add,'добавить':self.add,'clear':self.clear,'очистить':self.clear,
                   'count':self.count,'количество':self.count,'get':self.get,'получить':self.get}
        if key in methods: return HostFunction(name,methods[key])
        return super().get_member(name)
    def set_member(self, name, value):
        self._mutable()
        if name.casefold() not in ('write','записывать'): raise ValueError('movement property is read-only')
        if type(value) is not bool: raise TypeError('Write requires Boolean')
        self._selected = value


class BSLRecorderCollection(BSLObject):
    def __str__(self): raise ValueError('movement collection presentation is unsupported')
    def __init__(self, document, schemas):
        self._sets = {schema.name.casefold():BSLRecorderSet(document,schema) for schema in schemas}
    def get_member(self, name):
        if name.casefold() not in self._sets: raise ValueError('recorder register not declared')
        return self._sets[name.casefold()]
