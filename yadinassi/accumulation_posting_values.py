"""Closed document-owned accumulation buffers, not a register manager API.

Only Active=true writes are admitted. Inactive movements remain deferred; this
is a profile restriction, not a universal native prohibition on inactive rows.
Duplicate dimensions and periods remain distinct recorder/line occurrences.
"""
from decimal import Decimal

from .accumulation_movements import (AccumulationDirection, AccumulationMovementRow,
                                    AccumulationReplacement)
from .catalog_backend import BackendError
from .dates import BSLDate
from .document_posting_values import BSLRecorderRow, BSLRecorderSet
from .documents import _date
from .transaction_backend import TransactionRequest
from .values import BSLObject


class _AccumulationRecordTypes(BSLObject):
    def __str__(self):
        raise ValueError('accumulation record type namespace presentation is unsupported')

    def get_member(self, name):
        values = {'receipt': AccumulationDirection.RECEIPT,
                  'приход': AccumulationDirection.RECEIPT,
                  'expense': AccumulationDirection.EXPENSE,
                  'расход': AccumulationDirection.EXPENSE}
        if name.casefold() in values:
            return values[name.casefold()]
        return super().get_member(name)


ACCUMULATION_RECORD_TYPES = _AccumulationRecordTypes()


class BSLAccumulationRow(BSLRecorderRow):
    def __init__(self, owner):
        super().__init__(owner)
        self._period = BSLDate(0)
        self._direction = AccumulationDirection.RECEIPT
        self._written = False
        self._bytes += 64

    def get_member(self, name):
        self._check()
        key = name.casefold()
        if key in ('period', 'период'): return self._period
        if key in ('recordtype', 'виддвижения'): return self._direction
        # The detached Add default is measured. Persisted occurrence ordinals
        # belong to the raw query projection, not a dimension uniqueness key.
        if key in ('linenumber', 'номерстроки'):
            if self._written:
                raise ValueError('post-write detached LineNumber is outside this profile')
            return Decimal(0)
        return super().get_member(name)

    def set_member(self, name, value):
        self._check()
        self._owner._mutable()
        key = name.casefold()
        if key in ('period', 'период'):
            _date(value)
            self._period = value
            return
        if key in ('recordtype', 'виддвижения'):
            if type(value) is not AccumulationDirection:
                raise TypeError('RecordType requires AccumulationRecordType')
            self._direction = value
            return
        return super().set_member(name, value)


class BSLAccumulationSet(BSLRecorderSet):
    def write(self):
        super().write()
        for row in self._rows:
            row._written = True

    def add(self):
        self._mutable()
        row = BSLAccumulationRow(self)
        self._budget(row._bytes, 1)
        self._rows.append(row)
        self._bytes += row._bytes
        return row

    def _stored_rows(self):
        if any(row._active is not True for row in self._rows):
            raise BackendError('unsupported')
        manager, schema = self._document._manager, self._schema
        return tuple(AccumulationMovementRow(index, _date(row._period), row._active,
            row._direction, *(tuple(manager._stored(field, row._values[field.name.casefold()])
                for field in fields) for fields in
                (schema.dimensions, schema.resources, schema.attributes)))
            for index, row in enumerate(self._rows, 1))

    def _replace(self, transaction, rows):
        transaction._open()
        key = self._document._key
        snapshot = transaction.unit.read_accumulation(self._schema.identity, key).snapshot
        transaction.unit.stage(TransactionRequest('accumulation_replace',
            AccumulationReplacement(self._schema.identity, key, rows, snapshot)))


class BSLAccumulationCollection(BSLObject):
    def __init__(self, document, schemas):
        self._sets = {schema.name.casefold(): BSLAccumulationSet(document, schema)
                      for schema in schemas}

    def __str__(self):
        raise ValueError('accumulation movement collection presentation is unsupported')

    def get_member(self, name):
        if name.casefold() not in self._sets:
            raise ValueError('recorder accumulation register not declared')
        return self._sets[name.casefold()]
