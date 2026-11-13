"""Fresh, source-bound scalar constants persisted in an isolated SQLite file.

Only this exact source-bound format can be explicitly reopened; no migration. Only explicitly measured fresh
String defaults are persisted; other Get-before-Set operations fail. UUID and bounded local ValueStorage are explicitly typed; neither receives an inferred default.
This is a constants-only host capability, not
SQLiteDBContext and not activation of the configuration's other data objects.
"""
from decimal import Decimal
import hashlib
import json
import os
import sqlite3
import stat
from pathlib import Path
from .catalog_qualifiers import validate_string, normalize_number, bound_number
from .configuration_source import source_digest
from .configuration_source_constants import source_constant_definitions
from dataclasses import replace
from .dates import BSLDate, TICKS_PER_SECOND
from .sqlite_catalog import _private_parent

_PROFILE = 'source-scalar-constants-extensions-v3'
_MAX_DATABASE_BYTES = 1024 * 1024 * 1024
_MAX_ENCODED_BYTES = 65536
_MAX_NUMBER_TEXT = 256
# Native fresh-DB observations, not inferred defaults of unrelated scalar types.
_MEASURED_EMPTY_STRING_LENGTHS = frozenset({64})


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'))


def _definition_record(definition):
    record = [definition.kind, list(definition.qualifiers), list(definition.write_blockers)]
    if definition.type_dependencies:
        record.append(['defined_types', list(definition.type_dependencies)])
    return record


def _encode(value, definition):
    kind = definition.kind
    if kind == 'composite':
        if value is None:
            encoded = ['composite', ['undefined', None]]
        else:
            candidates = []
            for member_kind, member_qualifiers in definition.qualifiers:
                try:
                    candidates.append(json.loads(_encode(value, replace(definition, kind=member_kind, qualifiers=member_qualifiers))))
                except (ValueError, TypeError):
                    pass
            if len(candidates) != 1:
                raise TypeError('constant value does not fit its composite type')
            encoded = ['composite', candidates[0]]
    elif kind == 'enum_ref':
        from .enum_types import BSLEnumReference
        manager = definition.enum_namespace.get_member(definition.qualifiers[1])
        if (type(value) is not BSLEnumReference or value.value_type != manager._value_type
                or str(value.value_type.metadata_uuid) != definition.qualifiers[0]
                or (value.reference_uuid.int != 0 and str(value.reference_uuid) not in definition.qualifiers[2])):
            raise TypeError('constant enumeration reference belongs to another type or application')
        encoded = ['enum_ref', [definition.qualifiers[0], str(value.reference_uuid)]]
    elif kind == 'uuid':
        from .unique_identifiers import BSLUUID
        if type(value) is not BSLUUID or BSLUUID(value.text).text != value.text:
            raise TypeError('constant canonical UUID required')
        encoded = ['uuid', value.text]
    elif kind == 'value_storage':
        from .source_storage_codec import encode_storage
        encoded = ['value_storage', encode_storage(value)]
    elif kind == 'string':
        length = definition.qualifiers[0]
        validate_string(value, length or 65536)
        if definition.qualifiers[1:] == ('Fixed',) and len(value.encode('utf-16-le')) != length * 2:
            raise ValueError('constant Fixed String requires exact UTF-16 length')
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
        day = 86400 * TICKS_PER_SECOND
        fraction = definition.qualifiers[0]
        if ((fraction == 'Date' and value.ticks % day)
                or (fraction == 'Time' and value.ticks >= day)):
            raise ValueError('constant Date does not fit date fractions')
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
        if definition.kind == 'composite':
            if type(value) is not list or len(value) != 2:
                raise ValueError('constant storage integrity')
            if value == ['undefined', None]:
                value = None
            else:
                members = [(k, q) for k, q in definition.qualifiers if k == value[0]
                           and (k != 'enum_ref' or (type(value[1]) is list and len(value[1]) == 2 and q[0] == value[1][0]))]
                if len(members) != 1:
                    raise ValueError('constant storage integrity')
                k, q = members[0]
                value = _decode(_json(value), replace(definition, kind=k, qualifiers=q))
        elif definition.kind == 'enum_ref':
            from uuid import UUID
            if (type(value) is not list or len(value) != 2
                    or value[0] != definition.qualifiers[0] or type(value[1]) is not str):
                raise ValueError('constant storage integrity')
            identity = UUID(value[1])
            manager = definition.enum_namespace.get_member(definition.qualifiers[1])
            if identity.int == 0:
                value = manager._empty
            else:
                values = [v for v in manager._values if v.reference_uuid == identity]
                if len(values) != 1:
                    raise ValueError('constant storage integrity')
                value = values[0]
        elif definition.kind == 'uuid':
            from .unique_identifiers import BSLUUID
            value = BSLUUID(value)
        elif definition.kind == 'value_storage':
            from .source_storage_codec import decode_storage
            value = decode_storage(value)
        elif definition.kind == 'number':
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
    except (ValueError, TypeError, ArithmeticError, RecursionError, IndexError, KeyError, AttributeError):
        raise ValueError('constant storage integrity') from None


class SourceConstantStore:
    _explicit_transaction = False

    @property
    def transaction_active(self):
        return not self._closed and self._explicit_transaction

    def begin_transaction(self):
        self._open()
        if self._explicit_transaction:
            raise ValueError("nested source transactions are unsupported")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._open()
            self._explicit_transaction = True
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise

    def commit_transaction(self):
        if not self.transaction_active:
            raise ValueError("no active source transaction")
        try:
            self._open()
            self._connection.execute("COMMIT")
        except BaseException:
            if self._connection.in_transaction:
                self._connection.execute("ROLLBACK")
            raise
        finally:
            self._explicit_transaction = False

    def rollback_transaction(self):
        if not self.transaction_active:
            raise ValueError("no active source transaction")
        try:
            self._connection.execute("ROLLBACK")
        finally:
            self._explicit_transaction = False

    @classmethod
    def create(cls, path, source, *, enum_namespace=None):
        definitions, unsupported, names = source_constant_definitions(source, enum_namespace=enum_namespace)
        raw = os.fspath(path)
        if type(raw) is not str or not raw or raw.startswith(('file:', '//', '\\\\')) or '\x00' in raw:
            raise ValueError('invalid source constants destination')
        absolute = _private_parent(os.path.abspath(raw))
        source_sha = source_digest(source)
        rows = tuple(sorted((str(item.identity), item.name, _json(_definition_record(item))) for item in definitions))
        schema_sha = hashlib.sha256(_json([rows, sorted(unsupported.items()), list(names)]).encode()).hexdigest()
        binding = (_PROFILE, source_sha, str(source.config_uuid), schema_sha)
        fd = os.open(absolute, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        connection = None
        try:
            connection = sqlite3.connect(absolute, isolation_level=None, detect_types=0)
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA journal_mode=DELETE')
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            initial_epoch = connection.execute('PRAGMA data_version').fetchone()[0]
            for statement in _DDL:
                connection.execute(statement)
            connection.executemany('INSERT INTO source_file VALUES(?,?)', ((item.path, item.content) for item in source.files))
            connection.execute('INSERT INTO source_binding VALUES(1,?,?,?,?)', binding)
            connection.executemany('INSERT INTO constant_schema VALUES(?,?,?)', rows)
            initial = [(str(item.identity), _encode('', item)) for item in definitions
                       if item.kind == 'string' and not item.write_blockers and not item.type_dependencies
                       and item.qualifiers in tuple((n,) for n in _MEASURED_EMPTY_STRING_LENGTHS)]
            connection.executemany('INSERT INTO constant_value VALUES(?,?)', initial)
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
            result._identity = _file_identity(absolute)
            result._schema = _schema(connection)
            result._source = source
            result._verified_epoch = (initial_epoch if connection.execute('PRAGMA data_version').fetchone()[0] == initial_epoch else None)
            return result
        except BaseException as error:
            if connection is not None:
                connection.close()
            if isinstance(error, sqlite3.Error):
                raise ValueError('source constants creation failed; preserve the destination for inspection') from None
            # Preserve partial artifacts; never unlink a potentially replaced path.
            raise

    @classmethod
    def load_source(cls, path):
        """Read the embedded package without executing code or writing SQLite.

        The package is re-admitted by the ordinary XML/source importer. This
        method is not authentication: an owner able to rewrite the whole DB can
        replace both content and its digest. Reopen separately validates all
        constant values before any startup is allowed.
        """
        from .configuration_source import import_source, MAX_FILES, MAX_FILE_BYTES, MAX_TOTAL_BYTES
        raw = os.fspath(path)
        if type(raw) is not str or not raw or raw.startswith(('file:', '//', '\\\\')) or '\x00' in raw:
            raise ValueError('invalid source constants destination')
        absolute = _private_parent(os.path.abspath(raw))
        identity = _file_identity(absolute)
        if any(os.path.lexists(absolute + suffix) for suffix in ('-journal', '-wal', '-shm')):
            raise ValueError('source constants require clean-close database without sidecars')
        connection = None
        try:
            connection = sqlite3.connect(Path(absolute).as_uri() + '?mode=ro', uri=True,
                                         isolation_level=None, detect_types=0, timeout=0.2)
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('BEGIN')
            if _schema(connection) != _expected_schema():
                raise ValueError('source constants schema integrity')
            if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise ValueError('unsupported source constants journal')
            if connection.execute("SELECT count(*) FROM source_binding WHERE typeof(profile)!='text' OR length(CAST(profile AS BLOB))>128 OR typeof(source_sha256)!='text' OR length(CAST(source_sha256 AS BLOB))!=64 OR typeof(configuration_uuid)!='text' OR length(CAST(configuration_uuid AS BLOB))!=36").fetchone()[0]:
                raise ValueError('source constants embedded binding bound')
            binding = connection.execute('SELECT profile,source_sha256,configuration_uuid FROM source_binding LIMIT 2').fetchall()
            if len(binding) != 1 or binding[0][0] != _PROFILE:
                raise ValueError('source constants binding integrity')
            # Check SQL storage types and lengths before materializing BLOBs.
            sizes = connection.execute("SELECT length(content),typeof(content),typeof(path),length(path),length(CAST(path AS BLOB)) FROM source_file LIMIT ?", (MAX_FILES + 1,)).fetchall()
            if (not 1 <= len(sizes) <= MAX_FILES
                    or any(kind != 'blob' or path_kind != 'text' or not 1 <= path_size <= 1024 or path_bytes > 4096 or size > MAX_FILE_BYTES
                           for size, kind, path_kind, path_size, path_bytes in sizes)
                    or sum(size for size, _, _, _, _ in sizes) > MAX_TOTAL_BYTES):
                raise ValueError('source constants embedded source bound')
            files = dict(connection.execute('SELECT path,content FROM source_file ORDER BY path'))
            source = import_source(files)
            if binding[0][1:] != (source_digest(source), str(source.config_uuid)):
                raise ValueError('source constants embedded source digest integrity')
            if _file_identity(absolute) != identity:
                raise ValueError('source constants file identity changed')
            return source
        except sqlite3.Error:
            raise ValueError('source constants embedded source read refused') from None
        finally:
            if connection is not None:
                connection.close()

    @classmethod
    def update_source(cls, path, source):
        """Explicit additive source replacement; no BSL execution or type migration.

        Read/validate the previous embedded source and values, then repeat all
        integrity checks under a write reservation before atomically replacing
        source/binding/schema. Existing constant identity and value shape remain.
        """
        # Validate the new admitted source before opening a writable DB handle.
        digest = source_digest(source)
        definitions, unsupported, names = source_constant_definitions(source)
        previous = cls.load_source(path)
        if source.config_uuid != previous.config_uuid:
            raise ValueError('source update configuration identity mismatch')
        old_definitions, old_unsupported, old_names = source_constant_definitions(previous)
        old_meta = {item.name: item.identity for item in previous.metadata if item.family == 'Constant'}
        new_meta = {item.name: item.identity for item in source.metadata if item.family == 'Constant'}
        if any(new_meta.get(name) != identity for name, identity in old_meta.items()):
            raise ValueError('source update cannot remove, rename or replace constants')
        old_supported = {item.name: item for item in old_definitions}
        new_supported = {item.name: item for item in definitions}
        for name, old in old_supported.items():
            new = new_supported.get(name)
            if new is None or (new.identity, new.kind, new.qualifiers, new.type_dependencies) != (old.identity, old.kind, old.qualifiers, old.type_dependencies):
                raise ValueError('source update constant type/qualifier migration unsupported: ' + name)
        old_files = {item.path: item.content for item in previous.files}
        new_files = {item.path: item.content for item in source.files}
        for name in old_names:
            if name.casefold() in old_unsupported:
                key = 'Constants/' + name + '.xml'
                if old_files[key] != new_files.get(key):
                    raise ValueError('source update unsupported constant declaration changed: ' + name)
        rows = tuple(sorted((str(item.identity), item.name, _json(_definition_record(item))) for item in definitions))
        schema_sha = hashlib.sha256(_json([rows, sorted(unsupported.items()), list(names)]).encode()).hexdigest()
        binding = (_PROFILE, digest, str(source.config_uuid), schema_sha)
        known = {str(item.identity): item for item in definitions}
        old_ids = {str(item.identity) for item in old_definitions}
        initial = [(str(item.identity), _encode('', item)) for item in definitions
                   if str(item.identity) not in old_ids and item.kind == 'string'
                   and not item.write_blockers and not item.type_dependencies and item.qualifiers in tuple((n,) for n in _MEASURED_EMPTY_STRING_LENGTHS)]
        store = cls.reopen(path, previous)
        connection = store._connection
        try:
            connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            store._open()
            for table in ('source_extension_registry', 'source_extension_issues'):
                if connection.execute('SELECT 1 FROM ' + table + ' LIMIT 1').fetchone() is not None:
                    raise ValueError('source update populated extensions unsupported')
            values = connection.execute('SELECT identity,value_json FROM constant_value LIMIT ?', (len(old_definitions) + 1,)).fetchall()
            if len(values) > len(old_definitions) or any(identity not in old_ids for identity, _ in values):
                raise ValueError('source update existing value inventory integrity')
            for identity, raw in values:
                _decode(raw, known[identity])
            connection.execute('DELETE FROM source_file')
            connection.executemany('INSERT INTO source_file VALUES(?,?)', ((item.path, item.content) for item in source.files))
            connection.executemany('INSERT INTO constant_schema VALUES(?,?,?) ON CONFLICT(identity) DO UPDATE SET name=excluded.name,definition=excluded.definition', rows)
            connection.executemany('INSERT INTO constant_value VALUES(?,?)', initial)
            connection.execute('UPDATE source_binding SET profile=?,source_sha256=?,configuration_uuid=?,schema_sha256=? WHERE singleton=1', binding)
            # No handler or arbitrary code participates in updating the source.
            _verify_source(connection, source)
            if (connection.execute('SELECT profile,source_sha256,configuration_uuid,schema_sha256 FROM source_binding').fetchall() != [binding]
                    or tuple(connection.execute('SELECT identity,name,definition FROM constant_schema ORDER BY identity')) != rows
                    or _schema(connection) != store._schema
                    or _file_identity(store.path) != store._identity
                    or connection.execute('PRAGMA foreign_key_check').fetchone() is not None):
                raise ValueError('source update final integrity')
            page_bytes = connection.execute('PRAGMA page_count').fetchone()[0] * connection.execute('PRAGMA page_size').fetchone()[0]
            if page_bytes > _MAX_DATABASE_BYTES:
                raise ValueError('source update database size bound')
            connection.execute('COMMIT')
            return {'source_sha256': digest, 'preserved_values': len(values),
                    'added_constants': len(names) - len(old_names)}
        except BaseException as error:
            if connection.in_transaction:
                connection.execute('ROLLBACK')
            if isinstance(error, sqlite3.Error):
                raise ValueError('source update storage failure') from None
            raise
        finally:
            store.close()

    @classmethod
    def reopen(cls, path, source, *, enum_namespace=None):
        """Open only an unchanged source package's explicitly created scratch DB.

        A regular private file is required; mode=rw cannot create a missing file.
        Existing ordinary databases and previous scratch formats are refused.
        """
        raw = os.fspath(path)
        if type(raw) is not str or not raw or raw.startswith(('file:', '//', '\\\\')) or '\x00' in raw:
            raise ValueError('invalid source constants destination')
        absolute = _private_parent(os.path.abspath(raw))
        identity = _file_identity(absolute)
        connection = None
        try:
            if any(os.path.lexists(absolute + suffix) for suffix in ('-journal', '-wal', '-shm')):
                raise ValueError('source constants require clean-close database without sidecars')
            expected = _expected_schema()
            # Refuse foreign/hot databases before any writable SQLite handle.
            probe = sqlite3.connect(Path(absolute).as_uri() + '?mode=ro', uri=True, isolation_level=None, timeout=0.2)
            try:
                probe.execute('PRAGMA trusted_schema=OFF')
                if _schema(probe) != expected:
                    raise ValueError('source constants schema integrity')
            finally:
                probe.close()
            connection = sqlite3.connect(Path(absolute).as_uri() + '?mode=rw', uri=True,
                                         isolation_level=None, detect_types=0, timeout=0.2)
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA foreign_keys=ON')
            if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise ValueError('unsupported source constants journal')
            if _file_identity(absolute) != identity:
                raise ValueError('source constants file identity changed')
            # Compare exact DDL before querying application tables, including
            # rejecting injected triggers, views and indexes.
            expected = _expected_schema()
            if _schema(connection) != expected:
                raise ValueError('source constants schema integrity')
            definitions, unsupported, names = source_constant_definitions(source, enum_namespace=enum_namespace)
            rows = tuple(sorted((str(item.identity), item.name, _json(_definition_record(item))) for item in definitions))
            digest = source_digest(source)
            schema_sha = hashlib.sha256(_json([rows, sorted(unsupported.items()), list(names)]).encode()).hexdigest()
            result = object.__new__(cls)
            result.path, result.source_sha256, result.config_uuid = absolute, digest, source.config_uuid
            result.names, result.definitions = names, definitions
            result._definitions = {item.name.casefold(): item for item in definitions}
            result._unsupported = unsupported
            result._binding = (_PROFILE, digest, str(source.config_uuid), schema_sha)
            result._rows, result._connection, result._closed = rows, connection, False
            result._identity, result._schema, result._source = identity, expected, source
            result._verified_epoch = None
            epoch = connection.execute('PRAGMA data_version').fetchone()[0]
            connection.execute('BEGIN')
            try:
                result._open()
                known = {str(item.identity): item for item in definitions}
                values = connection.execute('SELECT identity,value_json FROM constant_value LIMIT ?',(len(definitions)+1,)).fetchall()
                if len(values) > len(definitions):
                    raise ValueError('source constants value inventory integrity')
                for key, value in values:
                    if key not in known:
                        raise ValueError('source constants value identity integrity')
                    _decode(value, known[key])
                if connection.execute('PRAGMA foreign_key_check').fetchone() is not None:
                    raise ValueError('source constants foreign key integrity')
            finally:
                connection.execute('ROLLBACK')
            if connection.execute('PRAGMA data_version').fetchone()[0] == epoch:
                result._verified_epoch = epoch
            result.require_empty_extension_registry()
            return result
        except BaseException as error:
            if connection is not None:
                connection.close()
            if isinstance(error, sqlite3.Error):
                raise ValueError('source constants reopen refused') from None
            raise

    def _open(self):
        if self._closed:
            raise ValueError('source constants store is closed')
        try:
            if _file_identity(self.path) != self._identity or _schema(self._connection) != self._schema:
                raise ValueError('source constants file/schema integrity')
            actual = self._connection.execute('SELECT profile,source_sha256,configuration_uuid,schema_sha256 FROM source_binding WHERE singleton=1').fetchall()
            rows = tuple(self._connection.execute('SELECT identity,name,definition FROM constant_schema ORDER BY identity'))
            if actual != [self._binding] or rows != self._rows:
                raise ValueError('source constants binding integrity')
            # Exact source bytes were verified at create/reopen. Own commits do
            # not change data_version; any external commit permanently retires
            # this cache for this handle. Never recache from a stale snapshot.
            epoch = self._connection.execute('PRAGMA data_version').fetchone()[0]
            if self._verified_epoch != epoch:
                self._verified_epoch = None
                _verify_source(self._connection, self._source)
        except sqlite3.Error:
            raise ValueError('source constants storage failure') from None

    def require_empty_extension_registry(self):
        self._open()
        owned = not self.transaction_active
        try:
            if owned:
                self._connection.execute('BEGIN')
            self._open()
            extensions = self._connection.execute('SELECT identity,source_archive FROM source_extension_registry LIMIT 1').fetchone()
            issues = self._connection.execute('SELECT identity,description FROM source_extension_issues LIMIT 1').fetchone()
            if extensions is not None or issues is not None:
                raise ValueError('populated extension registry is not supported by source host')
        except BaseException as error:
            if self.transaction_active:
                self.rollback_transaction()
            if isinstance(error, sqlite3.Error):
                raise ValueError('source extension registry storage failure') from None
            raise
        finally:
            if owned and self._connection.in_transaction:
                self._connection.execute('ROLLBACK')

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
        if self._closed:
            raise ValueError('source constants store is closed')
        owned = not self.transaction_active
        try:
            if owned:
                self._connection.execute('BEGIN')
            definition = self._definition(name)
            row = self._connection.execute('SELECT value_json FROM constant_value WHERE identity=?', (str(definition.identity),)).fetchone()
            if row is None:
                raise ValueError('uninitialized constant: ' + definition.name)
            return _decode(row[0], definition)
        except BaseException as error:
            if self.transaction_active:
                self.rollback_transaction()
            if isinstance(error, sqlite3.Error):
                raise ValueError('source constants storage failure') from None
            raise
        finally:
            if owned and self._connection.in_transaction:
                self._connection.execute('ROLLBACK')

    def set(self, name, value):
        return self._set(name, value, handled=False)

    def _set_after_handlers(self, name, value):
        return self._set(name, value, handled=True)

    def _set(self, name, value, *, handled):
        if self._closed:
            raise ValueError('source constants store is closed')
        owned = not self.transaction_active
        try:
            definition = self._definition(name)
            blockers = tuple(item for item in definition.write_blockers if not (handled and item == 'constant module execution is not supported'))
            if blockers:
                raise ValueError('unsupported constant write: ' + definition.name + ': ' + '; '.join(blockers))
            encoded = _encode(value, definition)
            if owned:
                self._connection.execute('BEGIN IMMEDIATE')
            self._open()
            self._connection.execute('INSERT INTO constant_value VALUES(?,?) ON CONFLICT(identity) DO UPDATE SET value_json=excluded.value_json', (str(definition.identity), encoded))
            if owned:
                self._connection.execute('COMMIT')
        except BaseException as error:
            if self._connection.in_transaction:
                self._connection.execute('ROLLBACK')
            self._explicit_transaction = False
            if isinstance(error, sqlite3.Error):
                raise ValueError('source constants storage failure') from None
            raise

    def get_many(self, names):
        """One read snapshot; callers publish the result only on complete success."""
        owned = not self.transaction_active
        try:
            if owned:
                self._connection.execute('BEGIN')
            self._open()
            result = {}
            for name in names:
                definition = self._definition(name)
                row = self._connection.execute('SELECT value_json FROM constant_value WHERE identity=?', (str(definition.identity),)).fetchone()
                if row is None:
                    raise ValueError('uninitialized constant: ' + definition.name)
                result[name.casefold()] = _decode(row[0], definition)
            return result
        except BaseException as error:
            if self.transaction_active:
                self.rollback_transaction()
            if isinstance(error, sqlite3.Error):
                raise ValueError('source constants storage failure') from None
            raise
        finally:
            if owned and self._connection.in_transaction:
                self._connection.execute('ROLLBACK')

    def set_many(self, values):
        """Atomic batch; never commit an enclosing explicit transaction."""
        owned = not self.transaction_active
        try:
            if owned:
                self.begin_transaction()
            for name, value in values.items():
                self.set(name, value)
            if owned:
                self.commit_transaction()
        except BaseException:
            if self.transaction_active:
                self.rollback_transaction()
            raise

    def close(self):
        if not self._closed:
            self._closed = True
            self._connection.close()


_DDL = ('CREATE TABLE source_binding(singleton INTEGER PRIMARY KEY CHECK(singleton=1), profile TEXT NOT NULL, source_sha256 TEXT NOT NULL, configuration_uuid TEXT NOT NULL, schema_sha256 TEXT NOT NULL)', 'CREATE TABLE constant_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)', 'CREATE TABLE constant_value(identity TEXT PRIMARY KEY REFERENCES constant_schema(identity), value_json TEXT NOT NULL CHECK(length(value_json)<=65536))', 'CREATE TABLE source_file(path TEXT PRIMARY KEY, content BLOB NOT NULL)', 'CREATE TABLE source_extension_registry(identity TEXT PRIMARY KEY, source_archive BLOB NOT NULL)', 'CREATE TABLE source_extension_issues(identity TEXT PRIMARY KEY, description TEXT NOT NULL)')


def _schema(connection):
    rows = connection.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name LIMIT 33").fetchall()
    if len(rows) > 32:
        raise ValueError('source constants schema bound')
    return tuple(rows)


def _expected_schema():
    connection = sqlite3.connect(':memory:')
    try:
        for sql in _DDL:
            connection.execute(sql)
        return _schema(connection)
    finally:
        connection.close()


def _file_identity(path):
    info = os.lstat(path)
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or getattr(info, 'st_file_attributes', 0) & 0x400
            or info.st_size > _MAX_DATABASE_BYTES):
        raise ValueError('source constants file integrity')
    if hasattr(os, 'getuid') and (info.st_uid != os.getuid() or info.st_mode & 0o022):
        raise ValueError('source constants private file required')
    return info.st_dev, info.st_ino


def _verify_source(connection, source):
    expected = sorted((item.path, item.content) for item in source.files)
    summary = connection.execute('SELECT count(*),coalesce(sum(length(content)),0),coalesce(max(length(content)),0) FROM source_file').fetchone()
    if summary != (len(expected), sum(len(v) for _, v in expected), max((len(v) for _, v in expected), default=0)):
        raise ValueError('source constants source integrity')
    cursor = connection.execute('SELECT path,content FROM source_file ORDER BY path')
    for row in expected:
        if cursor.fetchone() != row:
            raise ValueError('source constants source integrity')
    if cursor.fetchone() is not None:
        raise ValueError('source constants source integrity')
