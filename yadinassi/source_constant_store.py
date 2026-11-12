"""Fresh, source-bound scalar constants persisted in an isolated SQLite file.

No existing database is opened or migrated. No native default is invented:
Get before an explicit Set fails. This is a constants-only host capability, not
SQLiteDBContext and not activation of the configuration's other data objects.
"""
from decimal import Decimal
import hashlib
import json
import os
import sqlite3
from .catalog_qualifiers import validate_string, normalize_number, bound_number
from .configuration_source import source_digest
from .configuration_source_constants import source_constant_definitions
from .dates import BSLDate, TICKS_PER_SECOND
from .sqlite_catalog import _private_parent

_PROFILE = 'source-scalar-constants-v1'
_MAX_ENCODED_BYTES = 65536
_MAX_NUMBER_TEXT = 256


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


def _encode(value, definition):
    kind = definition.kind
    if kind == 'string':
        validate_string(value, definition.qualifiers[0])
        encoded = ['string', value]
    elif kind == 'boolean':
        if type(value) is not bool:
            raise TypeError('constant Boolean required')
        encoded = ['boolean', value]
    elif kind == 'number':
        bound_number(value)
        if normalize_number(value, definition.qualifiers) != value:
            raise ValueError('constant Number does not fit qualifiers')
        text = str(value)
        if len(text) > _MAX_NUMBER_TEXT:
            raise ValueError('constant Number text bound')
        encoded = ['number', text]
    elif kind == 'datetime':
        if type(value) is not BSLDate:
            raise TypeError('constant Date required')
        value.require_known()
        if value.ticks % TICKS_PER_SECOND:
            raise ValueError('constant Date requires whole seconds')
        encoded = ['datetime', str(value.ticks)]
    else:
        raise ValueError('unsupported constant type')
    text = _json(encoded)
    if len(text.encode('utf-8')) > _MAX_ENCODED_BYTES:
        raise ValueError('constant value byte bound')
    return text


def _decode(raw, definition):
    if type(raw) is not str or len(raw.encode('utf-8')) > _MAX_ENCODED_BYTES:
        raise ValueError('constant storage integrity')
    try:
        data = json.loads(raw)
        if type(data) is not list or len(data) != 2 or data[0] != definition.kind:
            raise ValueError('constant storage integrity')
        value = data[1]
        if definition.kind == 'number':
            if type(value) is not str or len(value) > _MAX_NUMBER_TEXT:
                raise ValueError('constant storage integrity')
            value = Decimal(value)
        elif definition.kind == 'datetime':
            if type(value) is not str or not value.isascii() or not value.isdigit() or len(value) > 20:
                raise ValueError('constant storage integrity')
            value = BSLDate(int(value))
        if _encode(value, definition) != raw:
            raise ValueError('constant storage integrity')
        return value
    except (ValueError, TypeError, ArithmeticError):
        raise ValueError('constant storage integrity') from None


class SourceConstantStore:
    @classmethod
    def create(cls, path, source):
        definitions, unsupported, names = source_constant_definitions(source)
        raw = os.fspath(path)
        if type(raw) is not str or not raw or raw.startswith(('file:', '//', '\\\\')) or '\x00' in raw:
            raise ValueError('invalid source constants destination')
        absolute = _private_parent(os.path.abspath(raw))
        source_sha = source_digest(source)
        rows = tuple(sorted((str(item.identity), item.name, _json([
            item.kind, list(item.qualifiers), list(item.write_blockers)])) for item in definitions))
        schema_sha = hashlib.sha256(_json([rows, sorted(unsupported.items()), list(names)]).encode()).hexdigest()
        binding = (_PROFILE, source_sha, str(source.config_uuid), schema_sha)
        fd = os.open(absolute, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        connection = None
        try:
            connection = sqlite3.connect(absolute, isolation_level=None, detect_types=0)
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA journal_mode=DELETE')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            connection.execute('CREATE TABLE source_binding(singleton INTEGER PRIMARY KEY CHECK(singleton=1), profile TEXT NOT NULL, source_sha256 TEXT NOT NULL, configuration_uuid TEXT NOT NULL, schema_sha256 TEXT NOT NULL)')
            connection.execute('CREATE TABLE constant_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)')
            connection.execute('CREATE TABLE constant_value(identity TEXT PRIMARY KEY REFERENCES constant_schema(identity), value_json TEXT NOT NULL CHECK(length(value_json)<=65536))')
            connection.execute('INSERT INTO source_binding VALUES(1,?,?,?,?)', binding)
            connection.executemany('INSERT INTO constant_schema VALUES(?,?,?)', rows)
            connection.execute('COMMIT')
            result = object.__new__(cls)
            result.path = absolute
            result.source_sha256 = source_sha
            result.config_uuid = source.config_uuid
            result.names = names
            result.definitions = definitions
            result._definitions = {item.name.casefold(): item for item in definitions}
            result._unsupported = unsupported
            result._binding, result._rows = binding, rows
            result._connection = connection
            result._closed = False
            return result
        except BaseException as error:
            if connection is not None:
                connection.close()
            if isinstance(error, sqlite3.Error):
                raise ValueError('source constants creation failed; preserve the destination for inspection') from None
            # Preserve partial artifacts; never unlink a potentially replaced path.
            raise

    def _open(self):
        if self._closed:
            raise ValueError('source constants store is closed')
        try:
            actual = self._connection.execute('SELECT profile,source_sha256,configuration_uuid,schema_sha256 FROM source_binding WHERE singleton=1').fetchall()
            rows = tuple(self._connection.execute('SELECT identity,name,definition FROM constant_schema ORDER BY identity'))
            if actual != [self._binding] or rows != self._rows:
                raise ValueError('source constants binding integrity')
        except sqlite3.Error:
            raise ValueError('source constants storage failure') from None

    def has(self, name):
        self._open()
        return type(name) is str and (name.casefold() in self._definitions or name.casefold() in self._unsupported)

    def _definition(self, name):
        self._open()
        if type(name) is not str or not 1 <= len(name) <= 128:
            raise TypeError('constant name requires String')
        key = name.casefold()
        if key in self._unsupported:
            raise ValueError('unsupported constant ' + name + ': ' + self._unsupported[key])
        if key not in self._definitions:
            raise ValueError('unknown constant: ' + name)
        return self._definitions[key]

    def get(self, name):
        definition = self._definition(name)
        try:
            row = self._connection.execute('SELECT value_json FROM constant_value WHERE identity=?', (str(definition.identity),)).fetchone()
        except sqlite3.Error:
            raise ValueError('source constants storage failure') from None
        if row is None:
            raise ValueError('uninitialized constant: ' + definition.name)
        return _decode(row[0], definition)

    def set(self, name, value):
        definition = self._definition(name)
        if definition.write_blockers:
            raise ValueError('unsupported constant write: ' + definition.name + ': ' + '; '.join(definition.write_blockers))
        encoded = _encode(value, definition)
        try:
            self._connection.execute('BEGIN IMMEDIATE')
            self._connection.execute('INSERT INTO constant_value VALUES(?,?) ON CONFLICT(identity) DO UPDATE SET value_json=excluded.value_json', (str(definition.identity), encoded))
            self._connection.execute('COMMIT')
        except sqlite3.Error:
            if self._connection.in_transaction:
                self._connection.execute('ROLLBACK')
            raise ValueError('source constants storage failure') from None

    def close(self):
        if not self._closed:
            self._closed = True
            self._connection.close()
