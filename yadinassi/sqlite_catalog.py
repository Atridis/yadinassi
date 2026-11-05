"""Owned SQLite catalog persistence. No native database format dependencies."""
import datetime
import decimal
import hashlib
import json
import os
import sqlite3
import stat
import sys
from uuid import UUID, uuid4
from pathlib import Path
from functools import wraps, cmp_to_key
from contextlib import contextmanager

from .configuration_import import _host_directory
from .sqlite_catalog_layout import (REGISTRY_DDL, MIGRATION_MARKER_DDL, build_layout, save_layout, load_layout, quote_identifier,
                                    catalog_ddl, index_ddls, encode_columns, decode_columns)
from .sqlite_catalog_sections import (SECTION_REGISTRY_DDL, build_section_layout, save_section_layout,
                                      load_section_layout, section_ddl)
from .catalog_backend import (BackendError, Capabilities, CatalogCard, CatalogDraft,
                              CatalogKey, CatalogSchema, CatalogSelection,
                              FieldSchema, Revision, CatalogComparison, CatalogPredicate,
                              CatalogOrder, CatalogScanRequest, CatalogPage, CatalogScalarRow,
                              CatalogValueRow, CatalogValuePage, TabularSectionSchema,
                              TabularRow, TabularSectionRows)

_APPLICATION_ID = 0x59414449
_MAX_ROWS = 10000
_MAX_FILES = 2048
_MAX_CONFIG_BYTES = 16 * 1024 * 1024
_MAX_DATABASE_BYTES = 256 * 1024 * 1024
_MAX_ROW_BYTES = 1024 * 1024
_MAX_SECTIONS = 16
_MAX_DATABASE_SECTIONS = 512
_MAX_SECTION_ROWS = 1000
_OWNER_BATCH = 128
_UNLOADED = object()


def _interruption(error):
    return not isinstance(error, Exception) or isinstance(error, MemoryError)


def _close_owned_connection(owner):
    if owner._connection is not None:
        # A failed close makes the owner unusable but does not prove that
        # SQLite released its locks. Retain ownership until close succeeds.
        owner._closed=True; owner._scan_cursor=None
        rollback_error=None
        try:
            if owner._connection.in_transaction: owner._connection.execute('ROLLBACK')
        except BaseException as error:
            rollback_error=error
        try:
            owner._connection.close()
        except BaseException as close_error:
            if rollback_error is not None and _interruption(rollback_error): raise rollback_error
            if isinstance(close_error,sqlite3.Error):raise BackendError('storage_error') from None
            raise
        else:
            owner._connection=None
            if owner._backend._active is owner: owner._backend._active=None
        if rollback_error is not None:
            if isinstance(rollback_error,sqlite3.Error):raise BackendError('storage_error') from None
            raise rollback_error


class _PendingConnection:
    """Close-only owner while a read/write view has not passed admission."""
    def __init__(self, backend):
        self._backend=backend; self._connection=None
        self._closed=True; self._scan_cursor=None

    def close(self):
        _close_owned_connection(self)
        # Failure before sqlite3.connect returned did not acquire a handle.
        if self._connection is None and self._backend._active is self:
            self._backend._active=None


def _boundary(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        except BackendError:
            raise
        except sqlite3.Error:
            raise BackendError('storage_error') from None
        except (ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
            raise BackendError('integrity') from None
    return call


def _revision_number(token):
    if type(token) is not str or not 1 <= len(token) <= 19 or not token.isascii() or not token.isdecimal() or token.startswith('0'):
        raise BackendError('conflict')
    result = int(token)
    if not 1 <= result < 2**63-1: raise BackendError('conflict')
    return result


def _private_parent(path):
    try:
        parent = _host_directory(os.path.dirname(path))
    except (OSError, ValueError):
        raise BackendError('invalid_input') from None
    info = os.stat(parent)
    # This is an owned-directory contract, not defence against a hostile same-user process.
    if hasattr(os, 'getuid') and (info.st_uid != os.getuid() or info.st_mode & 0o022):
        raise BackendError('invalid_input')
    return os.path.join(parent, os.path.basename(path))


def _uuid(value, *, empty=False):
    if type(value) is not UUID or (not empty and value.int == 0):
        raise BackendError('invalid_input')
    return str(value)


def _json(value):
    return json.dumps(value, ensure_ascii=True, separators=(',', ':'), allow_nan=False)


def _fields_data(fields_schema):
    if type(fields_schema) is not tuple or len(fields_schema) > 64:
        raise BackendError('invalid_input')
    names = {'code', 'description', 'deletionmark', 'ref'}
    ids = set()
    fields = []
    for field in fields_schema:
        if type(field) is not FieldSchema or type(field.name) is not str or not field.name or len(field.name) > 128:
            raise BackendError('invalid_input')
        identity = _uuid(field.identity)
        if identity in ids or field.name.casefold() in names:
            raise BackendError('invalid_input')
        ids.add(identity); names.add(field.name.casefold())
        if type(field.kind) is not str or field.kind not in ('string', 'number', 'boolean', 'datetime', 'catalog_ref') or type(field.qualifiers) is not tuple:
            raise BackendError('unsupported')
        q = field.qualifiers
        if field.kind == 'string' and (len(q) != 1 or type(q[0]) is not int or not 0 <= q[0] <= 65536):
            raise BackendError('invalid_input')
        if field.kind == 'number' and (len(q) != 3 or type(q[0]) is not int or type(q[1]) is not int or not 1 <= q[0] <= 38 or not 0 <= q[1] <= q[0] or type(q[2]) is not str or q[2] not in ('Any', 'Nonnegative')):
            raise BackendError('invalid_input')
        if field.kind == 'datetime' and (len(q) != 1 or type(q[0]) is not str or q[0] != 'DateTime'):
            raise BackendError('unsupported')
        if field.kind in ('boolean', 'catalog_ref') and q:
            raise BackendError('invalid_input')
        if field.kind == 'catalog_ref':
            _uuid(field.target_catalog_id)
        elif field.target_catalog_id is not None:
            raise BackendError('invalid_input')
        fields.append([identity, field.name, field.kind, list(field.qualifiers),
                       str(field.target_catalog_id) if field.target_catalog_id else None])
    return fields


def _schema_data(schema, *, enforce_serialized_limit=True):
    if type(schema) is not CatalogSchema or type(schema.tabular_sections) is not tuple:
        raise BackendError('invalid_input')
    _uuid(schema.identity)
    if type(schema.name) is not str or not schema.name or len(schema.name) > 128:
        raise BackendError('invalid_input')
    if any(type(n) is not int or not 0 <= n <= 1024 for n in (schema.code_length, schema.description_length)):
        raise BackendError('invalid_input')
    fields = _fields_data(schema.fields)
    result = [str(schema.identity), schema.name, schema.code_length, schema.description_length, fields]
    if len(schema.tabular_sections) > _MAX_SECTIONS: raise BackendError('invalid_input')
    names = {'code', 'description', 'deletionmark', 'ref'} | {f.name.casefold() for f in schema.fields}
    ids = {schema.identity} | {f.identity for f in schema.fields}
    sections = []
    for section in schema.tabular_sections:
        if type(section) is not TabularSectionSchema or type(section.name) is not str or not section.name or len(section.name) > 128:
            raise BackendError('invalid_input')
        identity = _uuid(section.identity)
        if section.identity in ids or section.name.casefold() in names: raise BackendError('invalid_input')
        names.add(section.name.casefold()); ids.add(section.identity)
        sections.append([identity, section.name, _fields_data(section.fields)])
    # Preserve the original five-element serialization for configurations without
    # sections, including existing stored definitions and migration fingerprints.
    if sections: result.append(sections)
    if enforce_serialized_limit and len(_json(result)) > 65536: raise BackendError('invalid_input')
    return result


def _schema(raw):
    if type(raw) is not str or len(raw) > 65536: raise BackendError('integrity')
    data = json.loads(raw)
    if type(data) is not list or len(data) not in (5, 6): raise BackendError('integrity')
    def identity(value):
        if type(value) is not str: raise BackendError('integrity')
        result = UUID(value)
        if str(result) != value or not result.int: raise BackendError('integrity')
        return result
    def fields(items):
        if type(items) is not list or len(items) > 64: raise BackendError('integrity')
        if any(type(f) is not list or len(f) != 5 or type(f[3]) is not list for f in items): raise BackendError('integrity')
        return tuple(FieldSchema(identity(f[0]), f[1], f[2], tuple(f[3]), identity(f[4]) if f[4] is not None else None) for f in items)
    sections = ()
    if len(data) == 6:
        if type(data[5]) is not list or not 1 <= len(data[5]) <= _MAX_SECTIONS: raise BackendError('integrity')
        if any(type(s) is not list or len(s) != 3 for s in data[5]): raise BackendError('integrity')
        sections = tuple(TabularSectionSchema(identity(s[0]), s[1], fields(s[2])) for s in data[5])
    result = CatalogSchema(identity(data[0]), data[1], data[2], data[3], fields(data[4]), sections)
    if _schema_data(result, enforce_serialized_limit=False) != data:
        raise BackendError('integrity')
    return result


def _all_fields(schema):
    return schema.fields + tuple(f for section in schema.tabular_sections for f in section.fields)


def _intent(draft, revision, values, sections):
    result = [str(draft.key.catalog_id), str(draft.key.record_id), draft.code,
              draft.description, draft.deletion_mark, values, revision]
    # Legacy drafts MUST retain their exact historical receipt hash. Explicit
    # replacement is a distinct intent, including an explicitly empty tuple.
    if sections is not None: result.append(['tabular_sections_v1', sections])
    return result


def _encode(value, field, database_id):
    kind, q = field.kind, field.qualifiers
    if kind == 'string':
        if type(value) is not str or len(q) != 1 or type(q[0]) is not int or len(value) > q[0]:
            raise BackendError('invalid_input')
        try: value.encode('utf-8')
        except UnicodeEncodeError: raise BackendError('invalid_input') from None
        return ['s', value]
    if kind == 'boolean':
        if type(value) is not bool: raise BackendError('invalid_input')
        return ['b', value]
    if kind == 'number':
        if type(value) is not decimal.Decimal or not value.is_finite() or len(q) != 3:
            raise BackendError('invalid_input')
        digits, scale, sign = q
        if type(digits) is not int or type(scale) is not int or not 1 <= digits <= 38 or not 0 <= scale <= digits:
            raise BackendError('invalid_input')
        # Fixed-point text is exact, never float or implicit SQLite NUMERIC affinity.
        with decimal.localcontext() as context:
            context.prec = 80
            quantum = decimal.Decimal(1).scaleb(-scale)
            try: quantized = value.quantize(quantum)
            except decimal.InvalidOperation: raise BackendError('invalid_input') from None
            if quantized != value or abs(value) >= decimal.Decimal(10) ** (digits-scale):
                raise BackendError('invalid_input')
        if sign == 'Nonnegative' and value < 0:
            raise BackendError('invalid_input')
        return ['n', format(quantized, 'f')]
    if kind == 'datetime':
        if type(value) is not datetime.datetime or value.tzinfo is not None or value.microsecond != 0:
            raise BackendError('invalid_input')
        return ['d', '%04d%02d%02d%02d%02d%02d' % (value.year,value.month,value.day,value.hour,value.minute,value.second)]
    if kind == 'catalog_ref':
        if type(value) is not CatalogKey or value.database_id != database_id or value.catalog_id != field.target_catalog_id:
            raise BackendError('invalid_input')
        _uuid(value.record_id, empty=True)
        return ['r', str(value.catalog_id), str(value.record_id)]
    raise BackendError('unsupported')


def _decode(value, field, database_id):
    if type(value) is not list or not value: raise BackendError('integrity')
    tag = value[0]
    try:
        if tag == 's' and len(value) == 2: result = value[1]
        elif tag == 'b' and len(value) == 2: result = value[1]
        elif tag == 'n' and len(value) == 2: result = decimal.Decimal(value[1])
        elif tag == 'd' and len(value) == 2 and type(value[1]) is str and len(value[1]) == 14:
            s = value[1]; result = datetime.datetime(int(s[:4]),int(s[4:6]),int(s[6:8]),int(s[8:10]),int(s[10:12]),int(s[12:]))
        elif tag == 'r' and len(value) == 3: result = CatalogKey(database_id, UUID(value[1]), UUID(value[2]))
        else: raise BackendError('integrity')
        if _encode(result, field, database_id) != value: raise BackendError('integrity')
        return result
    except (ValueError, TypeError, decimal.InvalidOperation):
        raise BackendError('integrity') from None


_DDL = (
    'CREATE TABLE database_info(singleton INTEGER PRIMARY KEY CHECK(singleton=1), database_uuid TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation>0), configuration_uuid TEXT NOT NULL, name TEXT NOT NULL, activated INTEGER NOT NULL CHECK(activated IN(0,1)), activation_issues TEXT NOT NULL)',
    'CREATE TABLE configuration_file(path TEXT PRIMARY KEY, kind TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL)',
    'CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE catalog_record(catalog_id TEXT NOT NULL REFERENCES catalog_schema(identity), record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), code TEXT NOT NULL, description TEXT NOT NULL, deletion_mark INTEGER NOT NULL CHECK(deletion_mark IN(0,1)), values_json TEXT NOT NULL, PRIMARY KEY(catalog_id,record_id), UNIQUE(catalog_id,code))',
    'CREATE TABLE commit_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, revisions_json TEXT NOT NULL)',
)


class SQLiteCatalogBackend:
    """Host-owned local file; one active view/writer per backend instance."""
    @_boundary
    def __init__(self, path, *, read_only=False):
        raw = os.fspath(path)
        if type(raw) is not str or not raw or '\x00' in raw or raw.startswith(('file:', '//', '\\\\')):
            raise BackendError('invalid_input')
        if type(read_only) is not bool: raise BackendError('invalid_input')
        self.read_only = read_only
        self.path = _private_parent(os.path.abspath(raw))
        self._closed = False
        self._active = None
        self._check_file()
        connection = self._connect()
        try:
            connection.execute('BEGIN')  # Pin schema, registry and metadata to one snapshot.
            if connection.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID:
                raise BackendError('unsupported')
            self.storage_version = connection.execute('PRAGMA user_version').fetchone()[0]
            if self.storage_version not in (1, 2, 3): raise BackendError('unsupported')
            statements = list(_DDL)
            if self.storage_version >= 2:
                statements = [x for x in statements if not x.startswith('CREATE TABLE catalog_record(')]
                malformed = connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR typeof(name)!='text' OR typeof(definition)!='text' OR length(CAST(identity AS BLOB))>36 OR length(CAST(name AS BLOB))>512 OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone()
                if malformed: raise BackendError('integrity')
                count, total = connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(identity AS BLOB))+length(CAST(name AS BLOB))+length(CAST(definition AS BLOB))),0) FROM catalog_schema").fetchone()
                if not 1 <= count <= 512 or total > _MAX_CONFIG_BYTES: raise BackendError('integrity')
                rows = connection.execute('SELECT identity,name,definition FROM catalog_schema LIMIT 513').fetchall()
                if not 1 <= len(rows) <= 512: raise BackendError('integrity')
                schemas = tuple(_schema(definition) for _,_,definition in rows)
                if any((identity,name) != (str(schema.identity),schema.name) for (identity,name,_),schema in zip(rows,schemas)):
                    raise BackendError('integrity')
                if len({schema.identity for schema in schemas}) != len(schemas): raise BackendError('integrity')
                section_count = sum(len(s.tabular_sections) for s in schemas)
                if section_count > _MAX_DATABASE_SECTIONS or (self.storage_version == 2 and section_count):
                    raise BackendError('unsupported')
                ids = {schema.identity for schema in schemas}
                if any(f.target_catalog_id not in ids for schema in schemas for f in _all_fields(schema) if f.kind == 'catalog_ref'): raise BackendError('integrity')
                self._layout = load_layout(connection, schemas)
                self._schemas = schemas
                self._schema_snapshot = tuple(rows)
                statements.extend(REGISTRY_DDL)
                statements.append(MIGRATION_MARKER_DDL)
                statements.extend(catalog_ddl(schema, self._layout) for schema in schemas)
                if self.storage_version == 3:
                    self._section_layout = load_section_layout(connection, schemas, self._layout)
            expected = {statement.split('(')[0].split()[-1]: statement for statement in statements[:len(_DDL) - (1 if self.storage_version >= 2 else 0)]}
            if self.storage_version >= 2:
                expected.update({statement.split('(')[0].split()[-1]: statement for statement in (*REGISTRY_DDL, MIGRATION_MARKER_DDL)})
                expected.update({self._layout.table_name(schema.identity): catalog_ddl(schema, self._layout) for schema in schemas})
                if self.storage_version == 3:
                    expected.update({statement.split('(')[0].split()[-1]: statement for statement in SECTION_REGISTRY_DDL})
                    expected.update({self._section_layout.table_name(schema.identity, section.identity):
                                     section_ddl(schema, section, self._layout, self._section_layout)
                                     for schema in schemas for section in schema.tabular_sections})
            # Bound all schema text before fetching it, including unexpected objects.
            if connection.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone(): raise BackendError('unsupported')
            objects, schema_bytes = connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(name AS BLOB))+length(CAST(COALESCE(sql,'') AS BLOB))),0) FROM sqlite_master").fetchone()
            if objects > 4096 or schema_bytes > 64 * 1024 * 1024: raise BackendError('unsupported')
            actual = {name: sql for name,sql in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7)) != 'sqlite_'")}
            if actual != expected or connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone() or (self.storage_version >= 2 and connection.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND sql IS NOT NULL LIMIT 1").fetchone()):
                raise BackendError('unsupported')
            row = connection.execute('SELECT database_uuid,generation,activated,activation_issues FROM database_info WHERE singleton=1').fetchone()
            self.activated = row[2] == 1
            if type(row[3]) is not str or len(row[3]) > 65536: raise BackendError('integrity')
            issues = json.loads(row[3])
            if type(issues) is not list or len(issues) > 2048 or any(type(v) is not str or len(v) > 1024 for v in issues): raise BackendError('integrity')
            self.activation_issues = tuple(issues)
            if type(row[2]) is not int or row[2] not in (0,1) or any(type(v) is not str for v in self.activation_issues) or (self.activated and self.activation_issues): raise BackendError('integrity')
            self.database_id = UUID(row[0]); self.configuration_generation = row[1]
            self._sqlite_schema_version = connection.execute('PRAGMA schema_version').fetchone()[0]
            _uuid(self.database_id)
        except BackendError: raise
        except (sqlite3.Error, TypeError, ValueError):
            raise BackendError('integrity') from None
        finally: connection.close()

    def _check_file(self):
        try:
            info = os.lstat(self.path)
            if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_nlink != 1 or info.st_size > _MAX_DATABASE_BYTES:
                raise BackendError('invalid_input')
            _private_parent(self.path)
        except OSError: raise BackendError('storage_error') from None

    def _connect(self, *, _owner=None):
        self._check_file()
        connection = None
        try:
            connection = sqlite3.connect(Path(self.path).as_uri() + ('?mode=ro' if self.read_only else '?mode=rw'), uri=True, isolation_level=None, detect_types=0, timeout=0.2)
            if _owner is not None: _owner._connection=connection
            if self.read_only: connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA synchronous=FULL')
            if not self.read_only:
                page_size = connection.execute('PRAGMA page_size').fetchone()[0]
                connection.execute('PRAGMA max_page_count=%d' % (_MAX_DATABASE_BYTES // page_size))
            if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise BackendError('unsupported')
            if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise BackendError('unsupported')
            return connection
        except BaseException:
            if _owner is not None:
                # The caller already reserved ownership. Let its failure path
                # close the handle without losing it or replacing this error.
                if connection is not None: _owner._connection=connection
            elif connection is not None: connection.close()
            raise

    @classmethod
    @_boundary
    def create(cls, path, configuration, *, activate=True):
        """Create only a new owned file, atomically import admitted XML and code."""
        from .configuration_xml import ConfigurationImport, ConfigurationFile, ConfigurationModule
        if type(configuration) is not ConfigurationImport or type(configuration.catalogs) is not tuple or type(configuration.files) is not tuple or type(configuration.modules) is not tuple or type(configuration.activation_issues) is not tuple:
            raise BackendError('invalid_input')
        if type(activate) is not bool: raise BackendError('invalid_input')
        if activate and configuration.activation_issues: raise BackendError('unsupported')
        if len(configuration.activation_issues) > 2048 or any(type(v) is not str or len(v) > 1024 for v in configuration.activation_issues) or len(_json(configuration.activation_issues)) > 65536: raise BackendError('invalid_input')
        if type(configuration.name) is not str or not configuration.name or len(configuration.name) > 128:
            raise BackendError('invalid_input')
        if any(type(f) is not ConfigurationFile for f in configuration.files) or any(type(m) is not ConfigurationModule for m in configuration.modules):
            raise BackendError('invalid_input')
        schemas = tuple(configuration.catalogs)
        if not 1 <= len(schemas) <= 512: raise BackendError('invalid_input')
        definitions = [_schema_data(s) for s in schemas]
        section_count = sum(len(s.tabular_sections) for s in schemas)
        if section_count > _MAX_DATABASE_SECTIONS or sum(len(_json(d)) for d in definitions) > _MAX_CONFIG_BYTES:
            raise BackendError('invalid_input')
        storage_version = 3 if section_count else 2
        identities = {s.identity for s in schemas}
        if len(identities) != len(schemas): raise BackendError('invalid_input')
        if any(f.target_catalog_id not in identities for s in schemas for f in _all_fields(s) if f.kind == 'catalog_ref'):
            raise BackendError('invalid_input')
        files = tuple(configuration.files)
        if not 1 <= len(files) <= _MAX_FILES or sum(len(f.content) for f in files) > _MAX_CONFIG_BYTES:
            raise BackendError('invalid_input')
        if len({f.path for f in files}) != len(files): raise BackendError('invalid_input')
        for f in files:
            if type(f.kind) is not str or f.kind not in ('xml','module'): raise BackendError('invalid_input')
            if type(f.path) is not str or len(f.path) > 256 or f.path.startswith('/') or '\\' in f.path or ':' in f.path or '\x00' in f.path or any(p in ('','.', '..') for p in f.path.split('/')) or type(f.content) is not bytes or len(f.content) > 1024*1024:
                raise BackendError('invalid_input')
        raw = os.fspath(path)
        if type(raw) is not str or raw.startswith(('file:', '//', '\\\\')) or '\x00' in raw:
            raise BackendError('invalid_input')
        absolute = _private_parent(os.path.abspath(raw))
        connection = None
        commit_started = False
        try:
            fd = os.open(absolute, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except OSError: raise BackendError('storage_error') from None
        try:
            connection = sqlite3.connect(absolute, isolation_level=None, detect_types=0)
            connection.execute('PRAGMA foreign_keys=ON'); connection.execute('PRAGMA journal_mode=DELETE'); connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            for statement in _DDL:
                if not statement.startswith('CREATE TABLE catalog_record('): connection.execute(statement)
            for statement in (*REGISTRY_DDL, MIGRATION_MARKER_DDL): connection.execute(statement)
            if storage_version == 3:
                for statement in SECTION_REGISTRY_DDL: connection.execute(statement)
            connection.execute('INSERT INTO database_info VALUES(1,?,1,?,?,?,?)', (str(uuid4()), _uuid(configuration.config_uuid), configuration.name, int(activate), _json(configuration.activation_issues)))
            for definition in definitions:
                connection.execute('INSERT INTO catalog_schema VALUES(?,?,?)', (definition[0], definition[1], _json(definition)))
            reserved_names = tuple(ddl.split('(')[0].split()[-1] for ddl in SECTION_REGISTRY_DDL) if storage_version == 3 else ()
            layout = build_layout(schemas, reserved_names=reserved_names)
            save_layout(connection, layout)
            for schema in schemas:
                connection.execute(catalog_ddl(schema, layout))
                for statement in index_ddls(schema, layout): connection.execute(statement)
            if storage_version == 3:
                sections_layout = build_section_layout(schemas, layout)
                save_section_layout(connection, sections_layout)
                for schema in schemas:
                    for section in schema.tabular_sections:
                        connection.execute(section_ddl(schema, section, layout, sections_layout))
            for f in files:
                connection.execute('INSERT INTO configuration_file VALUES(?,?,?,?)', (f.path,f.kind,f.content,hashlib.sha256(f.content).hexdigest()))
            connection.execute('PRAGMA application_id=%d' % _APPLICATION_ID)
            connection.execute('PRAGMA user_version=%d' % storage_version)
            # From this point the commit may have taken effect, even if its
            # response or the subsequent close/open fails. Never unlink it.
            commit_started = True
            connection.execute('COMMIT')
            connection.close(); connection = None
            return cls(absolute)
        except BaseException as error:
            if connection is not None:
                try:
                    if connection.in_transaction: connection.execute('ROLLBACK')
                except BaseException as cleanup_error:
                    if _interruption(cleanup_error) and not _interruption(error): error=cleanup_error
                try:
                    connection.close()
                except BaseException as cleanup_error:
                    if _interruption(cleanup_error) and not _interruption(error): error=cleanup_error
            # Never unlink the reserved path on failure: another process may
            # have opened or changed even the same inode after our close.
            if commit_started and not _interruption(error):
                raise BackendError('uncertain_commit') from None
            raise error

    @_boundary
    def capabilities(self):
        return Capabilities(self.activated, self.activated and not self.read_only, self.activated and not self.read_only, self.activated and not self.read_only,
                            catalog_tabular_sections=self.activated and self.storage_version == 3)

    @_boundary
    def begin_read(self): return self._begin(None)
    @_boundary
    def begin_write(self, operation_id):
        if self.read_only: raise BackendError('unsupported')
        _uuid(operation_id)
        return self._begin(operation_id)

    def _begin(self, operation_id):
        if self._closed: raise BackendError('closed')
        if not self.activated: raise BackendError('unsupported')
        if self._active is not None: raise BackendError('busy')
        pending = _PendingConnection(self)
        try:
            self._active = pending
            connection = self._connect(_owner=pending)
            try:
                connection.execute('BEGIN IMMEDIATE' if operation_id is not None else 'BEGIN')
                if (connection.execute('PRAGMA user_version').fetchone()[0] != self.storage_version or
                    connection.execute('PRAGMA schema_version').fetchone()[0] != self._sqlite_schema_version):
                    raise BackendError('schema_changed')
                if self.storage_version >= 2:
                    if connection.execute('SELECT COUNT(*) FROM catalog_schema').fetchone()[0] != len(self._schema_snapshot): raise BackendError('schema_changed')
                    for identity, name, definition in self._schema_snapshot:
                        if not connection.execute('SELECT 1 FROM catalog_schema WHERE identity=? AND name=? AND definition=?', (identity,name,definition)).fetchone(): raise BackendError('schema_changed')
                    layout = load_layout(connection, self._schemas)
                    if layout._tables != self._layout._tables or layout._fields != self._layout._fields: raise BackendError('schema_changed')
                    if self.storage_version == 3:
                        section_layout = load_section_layout(connection, self._schemas, layout)
                        if section_layout._tables != self._section_layout._tables or section_layout._fields != self._section_layout._fields:
                            raise BackendError('schema_changed')
                view = _View(self, connection, operation_id)
            except sqlite3.OperationalError:
                raise BackendError('busy') from None
            self._active = view
            return view
        except BaseException as error:
            try:
                if self._active is not None: self._active.close()
            except BaseException as cleanup_error:
                if _interruption(cleanup_error) and not _interruption(error): raise
            raise

    @_boundary
    def inspect_storage_mapping(self):
        """Read-only SQLite physical names and their current logical identities."""
        if self.storage_version < 2: raise BackendError('unsupported')
        view = self.begin_read()
        try:
            return tuple((schema.identity, schema.name, self._layout.table_name(schema.identity),
                          tuple((f.identity, f.name, self._layout.field_name(schema.identity, f.identity)) for f in schema.fields))
                         for schema in view.catalogs())
        finally: view.close()

    @_boundary
    def inspect_section_storage_mapping(self):
        """Current metadata names alongside durable UUID-keyed SQLite names."""
        view = self.begin_read()
        try:
            if self.storage_version != 3:
                view.catalogs()  # Reject section metadata in legacy storage.
                return ()
            layout = self._section_layout
            return tuple((schema.identity, schema.name, section.identity, section.name,
                          layout.table_name(schema.identity, section.identity),
                          tuple((f.identity, f.name, layout.field_name(schema.identity, section.identity, f.identity))
                                for f in section.fields))
                         for schema in view.catalogs() for section in schema.tabular_sections)
        finally: view.close()

    @_boundary
    def export_configuration(self):
        if self._closed: raise BackendError('closed')
        connection = self._connect()
        try:
            # Pin preflight and payload reads to the same SQLite snapshot.
            connection.execute('BEGIN')
            count,total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
            if not 1 <= count <= _MAX_FILES or total > _MAX_CONFIG_BYTES: raise BackendError('integrity')
            result = {}
            for path, content, digest in connection.execute('SELECT path,content,sha256 FROM configuration_file ORDER BY path'):
                if type(content) is not bytes or type(path) is not str or len(path) > 256 or len(content) > 1024*1024 or hashlib.sha256(content).hexdigest() != digest: raise BackendError('integrity')
                result[path] = content
            return result
        finally: connection.close()

    @_boundary
    def resolve_write(self, operation_id, draft, expected_revision=None):
        # Resolve one catalog Write, binding the durable receipt to the exact intent.
        receipt = self.committed_operation(operation_id)
        if receipt is None: return None
        view = self.begin_read()
        try:
            values = view._draft(draft)
            sections = view._draft_sections(draft)
            if expected_revision is None:
                revision = 1
            else:
                r = expected_revision
                if type(r) is not Revision or (r.database_id,r.configuration_generation,r.catalog_id,r.record_id) != (self.database_id,self.configuration_generation,draft.key.catalog_id,draft.key.record_id) or type(r.token) is not str:
                    raise BackendError('conflict')
                revision = _revision_number(r.token) + 1
            intent = [_intent(draft, revision, values, sections)]
            digest = hashlib.sha256(_json(intent).encode('utf-8')).hexdigest()
            if digest != receipt[0] or len(receipt[1]) != 1:
                raise BackendError('conflict')
            return receipt[1][0]
        finally: view.close()

    @_boundary
    def committed_operation(self, operation_id):
        _uuid(operation_id)
        if self._closed: raise BackendError('closed')
        connection = self._connect()
        try:
            row = connection.execute('SELECT request_hash,revisions_json FROM commit_receipt WHERE operation_id=?', (str(operation_id),)).fetchone()
            if row is None: return None
            if type(row[0]) is not str or len(row[0]) != 64 or type(row[1]) is not str or len(row[1]) > _MAX_ROW_BYTES: raise BackendError('integrity')
            revisions = tuple(Revision(self.database_id,self.configuration_generation,UUID(c),UUID(r),v)
                              for c,r,v in json.loads(row[1]))
            return (row[0], revisions)
        finally: connection.close()

    def close(self):
        if self._active is not None: self._active.close()
        self._closed = True


class _View:
    def __init__(self, backend, connection, operation_id):
        self._backend, self._connection, self._operation_id = backend, connection, operation_id
        self._closed = False; self._changes = []; self._intents = []
        self._scan_cursor = None
        self._section_write_bytes = 0
        self._section_write_rows = 0
        row = connection.execute('SELECT database_uuid,generation FROM database_info WHERE singleton=1').fetchone()
        self.database_id, self.configuration_generation = UUID(row[0]), row[1]
        if operation_id is not None and connection.execute('SELECT 1 FROM commit_receipt WHERE operation_id=?',(str(operation_id),)).fetchone() is not None:
            raise BackendError('conflict')
        if self.database_id != backend.database_id or self.configuration_generation != backend.configuration_generation:
            raise BackendError('schema_changed')

    def _require(self, write=False, mutate=False):
        if self._closed: raise BackendError('closed')
        if write and self._operation_id is None: raise BackendError('unsupported')
        if mutate and len(self._changes) >= _MAX_ROWS: raise BackendError('unsupported')

    @_boundary
    def catalogs(self):
        self._require()
        rows = self._connection.execute('SELECT definition FROM catalog_schema ORDER BY name,identity').fetchall()
        if len(rows) > 512: raise BackendError('integrity')
        schemas = tuple(_schema(row[0]) for row in rows)
        if self._backend.storage_version < 3 and any(s.tabular_sections for s in schemas):
            raise BackendError('unsupported')
        return schemas

    @_boundary
    def catalog_schema(self, catalog_id):
        self._require(); _uuid(catalog_id)
        row = self._connection.execute('SELECT definition FROM catalog_schema WHERE identity=?', (str(catalog_id),)).fetchone()
        if row is None: raise BackendError('not_found')
        schema = _schema(row[0])
        if self._backend.storage_version < 3 and schema.tabular_sections: raise BackendError('unsupported')
        return schema

    def _scalar(self, catalog_id, row, *, schema):
        # Callers have already validated this schema in the same transaction.
        # Reuse it for every row without a per-card SELECT and JSON parse.
        if self._backend.storage_version == 1:
            if type(row[5]) is not str or len(row[5]) > _MAX_ROW_BYTES: raise BackendError('integrity')
            encoded = json.loads(row[5])
        else:
            encoded = decode_columns(row[5:], schema)
        if type(encoded) is not list: raise BackendError('integrity')
        if len(encoded) != len(schema.fields): raise BackendError('integrity')
        if type(row[1]) is not int or not 1 <= row[1] < 2**63 or type(row[2]) is not str or len(row[2]) > schema.code_length or type(row[3]) is not str or len(row[3]) > schema.description_length or type(row[4]) is not int or row[4] not in (0,1): raise BackendError('integrity')
        key = CatalogKey(self.database_id, catalog_id, UUID(row[0]))
        _uuid(key.record_id)
        revision = Revision(self.database_id,self.configuration_generation,catalog_id,key.record_id,str(row[1]))
        return CatalogScalarRow(key,revision,row[2],row[3],bool(row[4]),
                                tuple(_decode(v,f,self.database_id) for v,f in zip(encoded,schema.fields)))

    def _card(self, catalog_id, row, section_budget=None, *, schema, sections=_UNLOADED):
        scalar = self._scalar(catalog_id, row, schema=schema)
        if sections is _UNLOADED:
            sections = self._read_sections(schema, scalar.key.record_id, section_budget)
        return CatalogCard(scalar.key, scalar.revision, scalar.code, scalar.description,
                           scalar.deletion_mark, scalar.values, sections)

    def _section_source(self, schema, section):
        layout = self._backend._section_layout
        table = quote_identifier(layout.table_name(schema.identity, section.identity))
        fields = [quote_identifier(layout.field_name(schema.identity, section.identity, f.identity)) for f in section.fields]
        return table, fields

    def _read_sections(self, schema, record_id, budget=None):
        if not schema.tabular_sections: return ()
        if self._backend.storage_version != 3: raise BackendError('unsupported')
        if budget is None: budget = [0, 0]
        prepared = []; owner_count = owner_bytes = 0
        # Aggregate before materializing rows; a large selection must not turn
        # individually bounded cards into an unbounded nested result.
        for section in schema.tabular_sections:
            table, columns = self._section_source(schema, section)
            invalid = ["typeof(row_id)!='text'", "length(CAST(row_id AS BLOB))!=36",
                       "typeof(row_number)!='integer'", 'row_number<1', 'row_number>%d' % _MAX_SECTION_ROWS]
            lengths = ['36', '16']
            for field, column in zip(section.fields, columns):
                expected = 'integer' if field.kind == 'boolean' else 'text'
                nullable = field.kind == 'catalog_ref'
                invalid.append(f'({column} IS NOT NULL AND typeof({column})!=\'{expected}\')' if nullable else f'typeof({column})!=\'{expected}\'')
                limit = field.qualifiers[0] * 4 if field.kind == 'string' else (36 if nullable else 64)
                invalid.append('length(CAST(%s AS BLOB))>%d' % (column, limit))
                lengths.append('COALESCE(length(CAST(%s AS BLOB)),0)' % column)
            args = (str(record_id),)
            if self._connection.execute('SELECT 1 FROM %s WHERE owner_id=? AND (%s) LIMIT 1' % (table, ' OR '.join(invalid)), args).fetchone():
                raise BackendError('integrity')
            count, size = self._connection.execute('SELECT COUNT(*),COALESCE(SUM(%s),0) FROM %s WHERE owner_id=?' % ('+'.join(lengths), table), args).fetchone()
            owner_count += count; owner_bytes += size
            if owner_count > _MAX_SECTION_ROWS or owner_bytes > _MAX_ROW_BYTES: raise BackendError('unsupported')
            prepared.append((section, table, columns, count))
        budget[0] += owner_count; budget[1] += owner_bytes
        if budget[0] > _MAX_ROWS or budget[1] > _MAX_CONFIG_BYTES: raise BackendError('unsupported')
        result = []
        for section, table, columns, count in prepared:
            rows = self._connection.execute('SELECT row_id,row_number%s FROM %s WHERE owner_id=? ORDER BY row_number LIMIT ?' %
                ((',' + ','.join(columns)) if columns else '', table), (str(record_id), _MAX_SECTION_ROWS + 1)).fetchall()
            if len(rows) != count: raise BackendError('integrity')
            values = []
            for position, row in enumerate(rows, 1):
                identity = UUID(row[0]); _uuid(identity)
                if str(identity) != row[0] or row[1] != position: raise BackendError('integrity')
                encoded = decode_columns(row[2:], section)
                values.append(TabularRow(identity, tuple(_decode(v, f, self.database_id) for v, f in zip(encoded, section.fields))))
            result.append(TabularSectionRows(section.identity, tuple(values)))
        return tuple(result)

    def _source(self, schema):
        if self._backend.storage_version == 1:
            return ('catalog_record', 'record_id,revision,code,description,deletion_mark,values_json', 'catalog_id=?', (str(schema.identity),))
        fields = ','.join(quote_identifier(self._backend._layout.field_name(schema.identity, f.identity)) for f in schema.fields)
        return (quote_identifier(self._backend._layout.table_name(schema.identity)), 'record_id,revision,code,description,deletion_mark' + (',' + fields if fields else ''), '1', ())

    def _preflight_v2(self, schema, *, record_id=None, selection_limit=None):
        table, _, _, _ = self._source(schema)
        invalid = ["typeof(record_id)!='text'", "typeof(revision)!='integer'", "typeof(code)!='text'", "typeof(description)!='text'", "typeof(deletion_mark)!='integer'", "length(CAST(record_id AS BLOB))>36", "length(CAST(code AS BLOB))>%d" % (schema.code_length*4), "length(CAST(description AS BLOB))>%d" % (schema.description_length*4)]
        lengths = ['length(CAST(record_id AS BLOB))', 'length(CAST(code AS BLOB))', 'length(CAST(description AS BLOB))', '32']
        for field in schema.fields:
            col = quote_identifier(self._backend._layout.field_name(schema.identity, field.identity))
            expected = 'integer' if field.kind == 'boolean' else 'text'
            nullable = field.kind == 'catalog_ref'
            invalid.append(("(%s IS NOT NULL AND typeof(%s)!='%s')" if nullable else "typeof(%s)!='%s'") % ((col,col,expected) if nullable else (col,expected)))
            limit = field.qualifiers[0]*4 if field.kind == 'string' else (36 if nullable else 64)
            invalid.append('length(CAST(%s AS BLOB))>%d' % (col,limit))
            lengths.append('COALESCE(length(CAST(%s AS BLOB)),0)' % col)
        length = '+'.join(lengths)
        # A v1 database could contain non-ASCII JSON up to 1 Mi characters.
        # UTF-8 can need four bytes per character; keep point reads bounded.
        invalid.append('(%s)>%d' % (length,4 * _MAX_ROW_BYTES + 4 * 2048 + 128))
        if selection_limit is not None:
            table = '(SELECT * FROM %s ORDER BY code COLLATE BINARY,record_id LIMIT ?)' % table
            args = (selection_limit,)
            where = '1'
        else:
            where = '1' if record_id is None else 'record_id=?'
            args = () if record_id is None else (str(record_id),)
        if self._connection.execute('SELECT 1 FROM %s WHERE (%s) AND (%s) LIMIT 1' % (table,where,' OR '.join(invalid)), args).fetchone(): raise BackendError('integrity')
        count, total = self._connection.execute('SELECT COUNT(*),COALESCE(SUM(%s),0) FROM %s WHERE %s' % (length,table,where), args).fetchone()
        if type(count) is not int or type(total) is not int or count > _MAX_ROWS or total > _MAX_CONFIG_BYTES: raise BackendError('unsupported')
        return count

    @_boundary
    def select_catalog(self, catalog_id, request=CatalogSelection()):
        self._require(); schema = self.catalog_schema(catalog_id)
        if type(request) is not CatalogSelection or type(request.limit) is not int or not 1 <= request.limit <= _MAX_ROWS or request.order != 'code_then_identity':
            raise BackendError('unsupported')
        table, columns, where, args = self._source(schema)
        if self._backend.storage_version >= 2: self._preflight_v2(schema, selection_limit=request.limit+1)
        rows = self._connection.execute('SELECT %s FROM %s WHERE %s ORDER BY code COLLATE BINARY,record_id LIMIT ?' % (columns,table,where), args+(request.limit+1,)).fetchall()
        if len(rows) > request.limit: raise BackendError('unsupported')
        # Validate all selected scalars before section payloads. The selection
        # remains finite/eager, but section reads are batched by owner instead
        # of repeating shape/count/payload queries for every returned card.
        for row in rows: self._scalar(catalog_id,row,schema=schema)
        owners = tuple(str(UUID(row[0])) for row in rows)
        _, sections = self._section_scan(schema,owners,materialize=True,selected=owners)
        return tuple(self._card(catalog_id,row,schema=schema,
                     sections=sections[str(UUID(row[0]))]) for row in rows)

    def _scan_field(self, schema, field):
        if type(field) is str:
            kinds = {'ref': 'catalog_ref', 'code': 'string',
                     'description': 'string', 'deletion_mark': 'boolean'}
            if field not in kinds: raise BackendError('invalid_input')
            return kinds[field], schema.identity if field == 'ref' else None
        if type(field) is UUID:
            for item in schema.fields:
                if item.identity == field: return item.kind, item.target_catalog_id
        raise BackendError('invalid_input')

    def _scan_operand(self, kind, target, value):
        if kind == 'string':
            if type(value) is not str or len(value) > 65536: raise BackendError('invalid_input')
            try: value.encode('utf-8')
            except UnicodeEncodeError: raise BackendError('invalid_input') from None
        elif kind == 'number':
            if sys.implementation.name != 'cpython' or decimal.Decimal.__sizeof__ is object.__sizeof__: raise BackendError('unsupported')
            if type(value) is not decimal.Decimal or not value.is_finite() or value.__sizeof__() > 2048: raise BackendError('invalid_input')
            parts = value.as_tuple()
            if len(parts.digits) > 256 or abs(parts.exponent) > 1000: raise BackendError('invalid_input')
        elif kind == 'boolean':
            if type(value) is not bool: raise BackendError('invalid_input')
        elif kind == 'datetime':
            if type(value) is not datetime.datetime or value.tzinfo is not None or value.microsecond: raise BackendError('invalid_input')
        elif kind == 'catalog_ref':
            if type(value) is not CatalogKey or any(type(v) is not UUID for v in (value.database_id,value.catalog_id,value.record_id)): raise BackendError('invalid_input')
            self._key(value)
            if value.catalog_id != target: raise BackendError('invalid_input')
        else: raise BackendError('unsupported')

    def _scan_predicate(self, schema, predicate, budget, depth=0):
        budget[0] += 1
        if budget[0] > 64 or depth > 8: raise BackendError('unsupported')
        if type(predicate) is CatalogComparison:
            kind, target = self._scan_field(schema, predicate.field)
            if type(predicate.operator) is not str or predicate.operator not in ('eq','ne','lt','le','gt','ge'): raise BackendError('unsupported')
            if kind == 'catalog_ref' and predicate.operator not in ('eq','ne'): raise BackendError('unsupported')
            self._scan_operand(kind, target, predicate.value)
        elif type(predicate) is CatalogPredicate:
            if type(predicate.kind) is not str or predicate.kind not in ('and','or') or type(predicate.terms) is not tuple or not 1 <= len(predicate.terms) <= 64: raise BackendError('invalid_input')
            for term in predicate.terms: self._scan_predicate(schema, term, budget, depth+1)
        else: raise BackendError('invalid_input')

    @staticmethod
    def _scan_value(schema, card, field):
        if type(field) is str:
            return card.key if field == 'ref' else getattr(card, field)
        return card.values[next(i for i, item in enumerate(schema.fields) if item.identity == field)]

    def _scan_matches(self, schema, card, predicate, string_comparison):
        if predicate is None: return True
        if type(predicate) is CatalogPredicate:
            values = (self._scan_matches(schema,card,term,string_comparison) for term in predicate.terms)
            return all(values) if predicate.kind == 'and' else any(values)
        left = self._scan_value(schema,card,predicate.field); right = predicate.value
        if type(left) is str and string_comparison == 'casefold_v1':
            left, right = left.casefold(), right.casefold()
        op = predicate.operator
        if op == 'eq': return left == right
        if op == 'ne': return left != right
        if op == 'lt': return left < right
        if op == 'le': return left <= right
        if op == 'gt': return left > right
        return left >= right

    def _validate_scan_scalars(self, catalog_id, schema, *, retain_owners=False):
        # Filtering must not hide corrupted owner values. This pass retains no
        # payload or card; coarse bounds run before the first payload fetch.
        if self._backend.storage_version >= 2:
            count = self._preflight_v2(schema)
        else:
            malformed = self._connection.execute(
                "SELECT 1 FROM catalog_record WHERE catalog_id=? AND ("
                "typeof(revision)!='integer' OR typeof(deletion_mark)!='integer' OR "
                "typeof(record_id)!='text' OR typeof(code)!='text' OR "
                "typeof(description)!='text' OR typeof(values_json)!='text' OR "
                "length(CAST(record_id AS BLOB))>36 OR "
                "length(CAST(code AS BLOB))>? OR length(CAST(description AS BLOB))>? OR "
                "length(CAST(values_json AS BLOB))>?) LIMIT 1",
                (str(catalog_id),schema.code_length*4,schema.description_length*4,_MAX_ROW_BYTES)).fetchone()
            if malformed is not None: raise BackendError('integrity')
            count, raw_bytes = self._connection.execute(
                'SELECT COUNT(*), COALESCE(SUM(length(CAST(record_id AS BLOB)) + '
                'length(CAST(code AS BLOB)) + length(CAST(description AS BLOB)) + '
                'length(CAST(values_json AS BLOB)) + 32),0) '
                'FROM catalog_record WHERE catalog_id=?', (str(catalog_id),)).fetchone()
            if type(count) is not int or type(raw_bytes) is not int or count > _MAX_ROWS or raw_bytes > _MAX_CONFIG_BYTES: raise BackendError('unsupported')
        table, columns, where, args = self._source(schema)
        owners = set(); seen = 0
        for row in self._connection.execute('SELECT %s FROM %s WHERE %s LIMIT ?' %
                (columns, table, where), args + (_MAX_ROWS + 1,)):
            scalar = self._scalar(catalog_id, row, schema=schema)
            if retain_owners: owners.add(str(scalar.key.record_id))
            seen += 1
        if seen != count: raise BackendError('integrity')
        return owners

    def _scan_sql(self, schema, request):
        # Legacy index iteration can determine stable order for UUID aliases;
        # retain that complete historical path instead of mixing SQL sort rules.
        if self._backend.storage_version == 1: return None
        # Python-defined comparisons preserve the existing versioned semantics;
        # SQLite never coerces Decimal to float or substitutes ASCII NOCASE.
        def compare(a, b): return (a > b) - (a < b)
        self._connection.create_collation('yadinassi_casefold_v1',
            lambda a, b: compare(a.casefold(), b.casefold()))
        self._connection.create_collation('yadinassi_decimal_v1',
            lambda a, b: compare(decimal.Decimal(a), decimal.Decimal(b)))
        self._connection.create_collation('yadinassi_uuid_v1',
            lambda a, b: compare(UUID(a).int, UUID(b).int))

        def field_sql(field):
            kind, _ = self._scan_field(schema, field)
            if type(field) is str:
                column = quote_identifier('record_id' if field == 'ref' else field)
            else:
                if self._backend.storage_version == 1: return None
                column = quote_identifier(self._backend._layout.field_name(schema.identity, field))
            if kind == 'catalog_ref':
                # Empty references are SQL NULL, but logical comparisons are
                # two-valued and compare the zero UUID just like Python.
                column = "COALESCE(%s,'00000000-0000-0000-0000-000000000000')" % column
                collation = 'yadinassi_uuid_v1'
            elif kind == 'number': collation = 'yadinassi_decimal_v1'
            elif kind == 'string' and request.string_comparison == 'casefold_v1':
                collation = 'yadinassi_casefold_v1'
            else: collation = 'BINARY'
            return column + ' COLLATE ' + collation

        def predicate_sql(predicate):
            if predicate is None: return '1', ()
            if type(predicate) is CatalogPredicate:
                terms = [predicate_sql(term) for term in predicate.terms]
                if any(term is None for term in terms): return None
                return ('(' + (' AND ' if predicate.kind == 'and' else ' OR ').join(
                    term[0] for term in terms) + ')', tuple(v for term in terms for v in term[1]))
            column = field_sql(predicate.field)
            if column is None: return None
            value = predicate.value
            if type(value) is CatalogKey: value = str(value.record_id)
            elif type(value) is decimal.Decimal: value = str(value)
            elif type(value) is datetime.datetime:
                value = '%04d%02d%02d%02d%02d%02d' % (value.year,value.month,value.day,value.hour,value.minute,value.second)
            elif type(value) is bool: value = int(value)
            operator = {'eq':'=', 'ne':'!=', 'lt':'<', 'le':'<=', 'gt':'>', 'ge':'>='}[predicate.operator]
            return '(' + column + ' ' + operator + ' ?)', (value,)

        predicate = predicate_sql(request.predicate)
        order = []
        for item in request.order:
            column = field_sql(item.field)
            if column is None: return None
            order.append(column + (' DESC' if item.descending else ' ASC'))
        if predicate is None: return None
        order.append('record_id COLLATE yadinassi_uuid_v1 ASC')
        # Preserve stable source order even for parseable noncanonical UUID
        # aliases, which the historical reader accepts as the same UUID value.
        order.append('rowid ASC')
        return predicate[0], predicate[1], ','.join(order)

    def _section_scan(self, schema, owners, *, materialize=False, selected=None, verified=False):
        """Validate in bounded batches, then stream or load only a result page.

        ``verified`` is private to an already validated pinned traversal. It
        avoids repeating aggregate checks when fetching its subsequent pages.
        """
        owners = tuple(sorted(set(owners)))
        totals = {owner: [0, 0] for owner in owners}
        result = {owner: [] for owner in owners} if materialize else None
        if not schema.tabular_sections: return totals, {owner: () for owner in owners}
        prepared = []
        for section in schema.tabular_sections:
            table, columns = self._section_source(schema, section)
            for offset in range(0, len(owners), _OWNER_BATCH):
                batch = owners[offset:offset + _OWNER_BATCH]
                where = 'owner_id IN (%s)' % ','.join('?' for _ in batch)
                expected_counts = None
                if not verified:
                    invalid = ["typeof(row_id)!='text'", "length(CAST(row_id AS BLOB))!=36",
                               "typeof(row_number)!='integer'", 'row_number<1', 'row_number>%d' % _MAX_SECTION_ROWS]
                    lengths = ['36', '16']
                    for field, column in zip(section.fields, columns):
                        expected = 'integer' if field.kind == 'boolean' else 'text'
                        nullable = field.kind == 'catalog_ref'
                        invalid.append(f"({column} IS NOT NULL AND typeof({column})!='{expected}')" if nullable else f"typeof({column})!='{expected}'")
                        limit = field.qualifiers[0] * 4 if field.kind == 'string' else (36 if nullable else 64)
                        invalid.append('length(CAST(%s AS BLOB))>%d' % (column, limit))
                        lengths.append('COALESCE(length(CAST(%s AS BLOB)),0)' % column)
                    if self._connection.execute('SELECT 1 FROM %s WHERE %s AND (%s) LIMIT 1' %
                            (table, where, ' OR '.join(invalid)), batch).fetchone():
                        raise BackendError('integrity')
                    expected_counts = {}
                    for owner, count, size in self._connection.execute(
                            'SELECT owner_id,COUNT(*),COALESCE(SUM(%s),0) FROM %s WHERE %s GROUP BY owner_id' %
                            ('+'.join(lengths), table, where), batch):
                        totals[owner][0] += count; totals[owner][1] += size
                        if totals[owner][0] > _MAX_SECTION_ROWS or totals[owner][1] > _MAX_ROW_BYTES:
                            raise BackendError('unsupported')
                        expected_counts[owner] = count
                prepared.append((section,table,columns,batch,where,expected_counts))
        if selected is not None: self._scan_section_budget(totals, selected)
        # All per-owner and filtered-result bounds precede payload validation.
        for section,table,columns,batch,where,expected_counts in prepared:
            counts = {}; rows_by_owner = {owner: [] for owner in batch} if materialize else None
            for row in self._connection.execute('SELECT owner_id,row_id,row_number%s FROM %s WHERE %s ORDER BY owner_id,row_number' %
                    ((',' + ','.join(columns)) if columns else '', table, where), batch):
                owner, raw_id, number = row[:3]
                identity = UUID(raw_id); _uuid(identity)
                position = counts.get(owner, 0) + 1
                if str(identity) != raw_id or number != position: raise BackendError('integrity')
                counts[owner] = position
                values = tuple(_decode(v, f, self.database_id) for v, f in
                               zip(decode_columns(row[3:], section), section.fields))
                if materialize: rows_by_owner[owner].append(TabularRow(identity, values))
            if expected_counts is not None and counts != expected_counts: raise BackendError('integrity')
            if materialize:
                for owner in batch:
                    result[owner].append(TabularSectionRows(section.identity, tuple(rows_by_owner[owner])))
        return totals, ({owner: tuple(parts) for owner, parts in result.items()} if materialize else None)

    @staticmethod
    def _scan_section_budget(totals, owners):
        rows = sum(totals[owner][0] for owner in owners)
        size = sum(totals[owner][1] for owner in owners)
        if rows > _MAX_ROWS or size > _MAX_CONFIG_BYTES: raise BackendError('unsupported')

    def _projection_columns(self, schema, fields):
        if fields is None: return None
        columns = ['record_id']
        for field in fields:
            if type(field) is str:
                columns.append(quote_identifier('record_id' if field == 'ref' else field))
            elif self._backend.storage_version == 1:
                return None
            else:
                columns.append(quote_identifier(self._backend._layout.field_name(schema.identity,field)))
        return ','.join(columns)

    def _projection_row(self, catalog_id, schema, fields, row):
        key = CatalogKey(self.database_id,catalog_id,UUID(row[0])); _uuid(key.record_id)
        values = []
        definitions = {field.identity: field for field in schema.fields}
        tags = {'string':'s', 'number':'n', 'datetime':'d'}
        for field, value in zip(fields,row[1:]):
            if type(field) is str:
                values.append(key if field == 'ref' else bool(value) if field == 'deletion_mark' else value)
                continue
            definition = definitions[field]
            if definition.kind == 'catalog_ref':
                encoded = ['r',str(definition.target_catalog_id),value if value is not None else str(UUID(int=0))]
            elif definition.kind == 'boolean':
                if type(value) is not int or value not in (0,1): raise BackendError('integrity')
                encoded = ['b',bool(value)]
            else: encoded = [tags[definition.kind],value]
            values.append(_decode(encoded,definition,self.database_id))
        return CatalogValueRow(key,tuple(values))

    @_boundary
    def scan_catalog(self, catalog_id, request):
        return self._scan_catalog(catalog_id, request, None)

    @_boundary
    def scan_catalog_values(self, catalog_id, request, fields):
        if type(fields) is not tuple or not 1 <= len(fields) <= 128:
            raise BackendError('invalid_input')
        return self._scan_catalog(catalog_id, request, fields)

    def _scan_catalog(self, catalog_id, request, fields):
        self._require()
        if self._operation_id is not None: raise BackendError('unsupported')
        schema = self.catalog_schema(catalog_id)
        if type(request) is not CatalogScanRequest or type(request.page_size) is not int or not 1 <= request.page_size <= 1000 or type(request.order) is not tuple or len(request.order) > 16: raise BackendError('invalid_input')
        if type(request.string_comparison) is not str or request.string_comparison not in ('codepoint','casefold_v1'): raise BackendError('unsupported')
        if request.predicate is not None: self._scan_predicate(schema,request.predicate,[0])
        if fields is not None:
            for field in fields: self._scan_field(schema, field)
        seen = set()
        for item in request.order:
            if type(item) is not CatalogOrder or type(item.descending) is not bool: raise BackendError('invalid_input')
            self._scan_field(schema,item.field)
            if item.field in seen: raise BackendError('invalid_input')
            seen.add(item.field)
        binding = (catalog_id,request.predicate,request.order,request.page_size,request.string_comparison,fields)
        table, columns, source_where, source_args = self._source(schema)
        plan = self._scan_sql(schema, request)
        if request.continuation is not None:
            if type(request.continuation) is not str or len(request.continuation) != 32: raise BackendError('invalid_input')
            cursor = self._scan_cursor
            if cursor is None or cursor[0] != request.continuation or cursor[1] != binding: raise BackendError('invalid_input')
            offset, fallback = cursor[2], cursor[3]
        else:
            self._scan_cursor = None
            owners = self._validate_scan_scalars(catalog_id, schema,
                retain_owners=fields is None and bool(schema.tabular_sections))
            fallback = None
            if plan is None:
                # Legacy v1 custom fields live in JSON. Keep the precise Python
                # comparator without depending on SQLite JSON extensions.
                fallback = []
                for row in self._connection.execute('SELECT %s FROM %s WHERE %s' % (columns,table,source_where),source_args):
                    scalar = self._scalar(catalog_id,row,schema=schema)
                    if self._scan_matches(schema,scalar,request.predicate,request.string_comparison): fallback.append((row,scalar))
                def compare(left, right):
                    for item in request.order:
                        a=self._scan_value(schema,left[1],item.field); b=self._scan_value(schema,right[1],item.field)
                        if type(a) is str and request.string_comparison == 'casefold_v1': a,b=a.casefold(),b.casefold()
                        if type(a) is CatalogKey: a,b=a.record_id.int,b.record_id.int
                        result=(a>b)-(a<b)
                        if result: return -result if item.descending else result
                    return (left[1].key.record_id.int>right[1].key.record_id.int)-(left[1].key.record_id.int<right[1].key.record_id.int)
                fallback = tuple(sorted(fallback,key=cmp_to_key(compare)))
            if fields is None and schema.tabular_sections:
                # Preserve full-card scans' historical corruption detection,
                # but charge nested-result budgets only to matching owners.
                if plan is None:
                    selected = [str(item[1].key.record_id) for item in fallback]
                else:
                    selected = [str(UUID(row[0])) for row in self._connection.execute(
                        'SELECT record_id FROM %s WHERE (%s) AND (%s)' % (table,source_where,plan[0]),source_args+plan[1])]
                self._section_scan(schema, owners, selected=selected)
            offset = 0
        projection_columns = self._projection_columns(schema,fields) if plan is not None else None
        if plan is None:
            rows = [item[0] for item in fallback[offset:offset+request.page_size+1]]
        else:
            rows = self._connection.execute('SELECT %s FROM %s WHERE (%s) AND (%s) ORDER BY %s LIMIT ? OFFSET ?' %
                (projection_columns or columns,table,source_where,plan[0],plan[2]),source_args+plan[1]+(request.page_size+1,offset)).fetchall()
        more = len(rows) > request.page_size
        rows = rows[:request.page_size]
        if fields is None:
            _, parts = self._section_scan(schema, (str(UUID(row[0])) for row in rows), materialize=True, verified=True)
            items = tuple(self._card(catalog_id,row,schema=schema,sections=parts[str(UUID(row[0]))]) for row in rows)
        else:
            items = []
            for row in rows:
                if projection_columns is not None:
                    items.append(self._projection_row(catalog_id,schema,fields,row))
                else:
                    scalar = self._scalar(catalog_id,row,schema=schema)
                    items.append(CatalogValueRow(scalar.key,tuple(self._scan_value(schema,scalar,field) for field in fields)))
            items = tuple(items)
        token = uuid4().hex if more else None
        self._scan_cursor = None if token is None else (token,binding,offset+len(rows),fallback)
        return CatalogPage(items,token) if fields is None else CatalogValuePage(items,token)

    @_boundary
    def read_catalog(self, key):
        self._require(); self._key(key)
        schema = self.catalog_schema(key.catalog_id)
        table, columns, where, args = self._source(schema)
        if self._backend.storage_version >= 2: self._preflight_v2(schema, record_id=key.record_id)
        row = self._connection.execute('SELECT %s FROM %s WHERE %s AND record_id=?' % (columns,table,where), args+(str(key.record_id),)).fetchone()
        return None if row is None else self._card(key.catalog_id,row,schema=schema)

    def _key(self,key):
        if type(key) is not CatalogKey or key.database_id != self.database_id: raise BackendError('invalid_input')
        _uuid(key.catalog_id); _uuid(key.record_id, empty=True)

    def _draft(self,draft):
        if type(draft) is not CatalogDraft: raise BackendError('invalid_input')
        self._key(draft.key); _uuid(draft.key.record_id)
        schema = self.catalog_schema(draft.key.catalog_id)
        if type(draft.code) is not str or len(draft.code)>schema.code_length or type(draft.description) is not str or len(draft.description)>schema.description_length or type(draft.deletion_mark) is not bool or type(draft.values) is not tuple or len(draft.values)!=len(schema.fields):
            raise BackendError('invalid_input')
        try:
            draft.code.encode('utf-8'); draft.description.encode('utf-8')
        except UnicodeEncodeError: raise BackendError('invalid_input') from None
        values = [_encode(v,f,self.database_id) for v,f in zip(draft.values,schema.fields)]
        for value in draft.values:
            if type(value) is CatalogKey and value.record_id.int and not self._reference_exists(value):
                raise BackendError('not_found')
        encoded = _json(values)
        if len(encoded.encode('utf-8')) > _MAX_ROW_BYTES: raise BackendError('invalid_input')
        return encoded

    def _reference_exists(self, key):
        schema = self.catalog_schema(key.catalog_id)
        table, _, where, args = self._source(schema)
        return self._connection.execute('SELECT 1 FROM %s WHERE %s AND record_id=?' % (table, where), args + (str(key.record_id),)).fetchone() is not None

    def _draft_sections(self, draft):
        sections = draft.tabular_sections
        if sections is None: return None
        if type(sections) is not tuple or len(sections) > _MAX_SECTIONS: raise BackendError('invalid_input')
        schema = self.catalog_schema(draft.key.catalog_id)
        if self._backend.storage_version != 3 and sections: raise BackendError('unsupported')
        by_id = {s.identity: s for s in schema.tabular_sections}
        supplied = {}; count = 0; size = 0; stored_size = 0
        for section in sections:
            if type(section) is not TabularSectionRows: raise BackendError('invalid_input')
            _uuid(section.section_id)
            if section.section_id not in by_id or section.section_id in supplied or type(section.rows) is not tuple:
                raise BackendError('invalid_input')
            count += len(section.rows)
            if count > _MAX_SECTION_ROWS: raise BackendError('invalid_input')
            definition = by_id[section.section_id]
            seen = set(); rows = []
            for row in section.rows:
                if type(row) is not TabularRow: raise BackendError('invalid_input')
                identity = _uuid(row.identity)
                if identity in seen or type(row.values) is not tuple or len(row.values) != len(definition.fields):
                    raise BackendError('invalid_input')
                seen.add(identity)
                values = [_encode(v, f, self.database_id) for v, f in zip(row.values, definition.fields)]
                for value in row.values:
                    if type(value) is CatalogKey and value.record_id.int and not self._reference_exists(value):
                        raise BackendError('not_found')
                encoded_row = [identity, values]
                size += len(_json(encoded_row)) + 1
                columns = encode_columns(values, definition)
                stored_size += 52 + sum(len(value.encode('utf-8')) if type(value) is str else (1 if type(value) is int else 0) for value in columns)
                if size > _MAX_ROW_BYTES or stored_size > _MAX_ROW_BYTES: raise BackendError('invalid_input')
                rows.append(encoded_row)
            supplied[section.section_id] = rows
        # Canonical order is UUID-based, independent of mutable metadata names
        # and caller ordering of sections. Row sequence remains significant.
        result = [[str(identity), supplied.get(identity, [])] for identity in sorted(by_id, key=lambda x: x.hex)]
        if len(_json(result)) > _MAX_ROW_BYTES: raise BackendError('invalid_input')
        return result

    def _replace_sections(self, draft, schema, sections):
        if sections is None or not schema.tabular_sections: return
        contents = dict(sections)
        for section in schema.tabular_sections:
            table, fields = self._section_source(schema, section)
            # Only explicit replacement removes section rows. The owner is
            # never deleted, including when its deletion mark is set.
            self._connection.execute('DELETE FROM %s WHERE owner_id=?' % table, (str(draft.key.record_id),))
            for position, (row_id, encoded) in enumerate(contents[str(section.identity)], 1):
                values = (str(draft.key.record_id), row_id, position) + encode_columns(encoded, section)
                columns = ['owner_id', 'row_id', 'row_number'] + fields
                self._connection.execute('INSERT INTO %s (%s) VALUES(%s)' % (table, ','.join(columns), ','.join('?' for _ in values)), values)

    @contextmanager
    def _atomic_record(self):
        # A caller may catch a failed write and still commit previous writes.
        # Never leave an owner update or partial row replacement behind.
        self._connection.execute('SAVEPOINT catalog_record_write')
        try:
            yield
            self._connection.execute('RELEASE catalog_record_write')
        except BaseException:
            try:
                self._connection.execute('ROLLBACK TO catalog_record_write')
                self._connection.execute('RELEASE catalog_record_write')
            except sqlite3.Error:
                self.close()
            raise

    def _section_write_budget(self, sections):
        if sections is not None:
            size = len(_json(sections))
            rows = sum(len(rows) for _, rows in sections)
            if self._section_write_bytes + size > _MAX_CONFIG_BYTES or self._section_write_rows + rows > _MAX_ROWS:
                raise BackendError('unsupported')

    @_boundary
    def create(self,draft):
        self._require(True, mutate=True); values = self._draft(draft)
        sections = self._draft_sections(draft); self._section_write_budget(sections)
        schema = self.catalog_schema(draft.key.catalog_id)
        table, columns, where, args = self._source(schema)
        if self._connection.execute('SELECT COUNT(*) FROM %s WHERE %s' % (table,where),args).fetchone()[0] >= _MAX_ROWS:
            raise BackendError('unsupported')
        with self._atomic_record():
            try:
                if self._backend.storage_version == 1:
                    self._connection.execute('INSERT INTO catalog_record VALUES(?,?,1,?,?,?,?)',(str(draft.key.catalog_id),str(draft.key.record_id),draft.code,draft.description,int(draft.deletion_mark),values))
                else:
                    vals = (str(draft.key.record_id),1,draft.code,draft.description,int(draft.deletion_mark))+encode_columns(json.loads(values),schema)
                    self._connection.execute('INSERT INTO %s (%s) VALUES(%s)' % (table,columns,','.join('?' for _ in vals)),vals)
            except sqlite3.IntegrityError:
                raise BackendError('duplicate_identity' if self._reference_exists(draft.key) else 'duplicate_code') from None
            self._replace_sections(draft, schema, sections)
        self._record_change(draft,1,values,sections)

    @_boundary
    def update(self,draft,expected_revision):
        self._require(True, mutate=True); values = self._draft(draft)
        sections = self._draft_sections(draft); self._section_write_budget(sections)
        r = expected_revision
        if type(r) is not Revision or (r.database_id,r.configuration_generation,r.catalog_id,r.record_id)!=(self.database_id,self.configuration_generation,draft.key.catalog_id,draft.key.record_id) or type(r.token) is not str:
            raise BackendError('conflict')
        revision = _revision_number(r.token)
        with self._atomic_record():
            try:
                schema = self.catalog_schema(draft.key.catalog_id)
                table, columns, where, args = self._source(schema)
                if self._backend.storage_version == 1:
                    cursor = self._connection.execute('UPDATE catalog_record SET revision=revision+1,code=?,description=?,deletion_mark=?,values_json=? WHERE catalog_id=? AND record_id=? AND revision=?',(draft.code,draft.description,int(draft.deletion_mark),values,str(draft.key.catalog_id),str(draft.key.record_id),revision))
                else:
                    sets = ['revision=revision+1','code=?','description=?','deletion_mark=?'] + [quote_identifier(self._backend._layout.field_name(schema.identity, f.identity))+'=?' for f in schema.fields]
                    vals = (draft.code,draft.description,int(draft.deletion_mark))+encode_columns(json.loads(values),schema)+args+(str(draft.key.record_id),revision)
                    cursor = self._connection.execute('UPDATE %s SET %s WHERE %s AND record_id=? AND revision=?' % (table,','.join(sets),where), vals)
            except sqlite3.IntegrityError: raise BackendError('duplicate_code') from None
            if cursor.rowcount != 1: raise BackendError('conflict')
            self._replace_sections(draft, schema, sections)
        self._record_change(draft,revision+1,values,sections)

    def _record_change(self,draft,revision,values,sections):
        self._changes.append(Revision(self.database_id,self.configuration_generation,draft.key.catalog_id,draft.key.record_id,str(revision)))
        self._intents.append(_intent(draft,revision,values,sections))
        if sections is not None:
            self._section_write_bytes += len(_json(sections))
            self._section_write_rows += sum(len(rows) for _, rows in sections)

    @_boundary
    def commit(self):
        self._require(True)
        revisions = tuple(self._changes)
        digest = hashlib.sha256(_json(self._intents).encode('utf-8')).hexdigest()
        try:
            self._connection.execute('INSERT INTO commit_receipt VALUES(?,?,?)',(str(self._operation_id),digest,_json([[str(r.catalog_id),str(r.record_id),r.token] for r in revisions])))
            self._connection.execute('COMMIT')
            self.close()
        except BaseException as error:
            # Caller must resolve persistent receipt after reopening, never blindly replay.
            try: self.close()
            except BaseException as cleanup_error:
                if _interruption(cleanup_error) and not _interruption(error): raise
            if _interruption(error): raise
            raise BackendError('uncertain_commit') from None
        return revisions

    def rollback(self): self.close()
    def close(self):
        _close_owned_connection(self)
