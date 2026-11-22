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
from threading import RLock
from contextlib import contextmanager
from dataclasses import replace

from yadinassi.configuration.configuration_import import _host_directory
from yadinassi.configuration.configuration_xml import (INERT_SOURCE_ISSUE, DEMO_KINDS_SOURCE_ISSUE, DEMO_KINDS_PROFILE,
                                DEMO_DIRECTORIES_SOURCE_ISSUE, DEMO_DIRECTORIES_PROFILE,
                                DEMO_PRODUCTS_SOURCE_ISSUE, DEMO_PRODUCTS_PROFILE)
from yadinassi.configuration.configuration_catalog_profile import CATALOG_FORMS_PROFILE, CATALOG_FORMS_SOURCE_ISSUE
from yadinassi.configuration.configuration_application_profile import APPLICATION_PROFILE, APPLICATION_SOURCE_ISSUE
from yadinassi.configuration.configuration_document_profile import DOCUMENT_FORMS_PROFILE, DOCUMENT_FORMS_SOURCE_ISSUE
from yadinassi.configuration.configuration_business_profile import BUSINESS_PROFILE, BUSINESS_SOURCE_ISSUE
from yadinassi.configuration.configuration_reference_profile import REFERENCE_PROFILE, REFERENCE_SOURCE_ISSUE
from yadinassi.db.catalog.catalog_backend import ConfigurationSourceIdentity, CatalogFormSource
from .sqlite_registers import (REGISTER_DDL, schema_data as register_schema_data,
    load_schemas as load_register_schemas, validate_configuration as validate_register_configuration, RegisterView, install_boundaries)
from .sqlite_documents import DOCUMENT_DDL, schema_data as document_schema_data, load_schemas as load_document_schemas, DocumentView
from .sqlite_document_layout import document_data_ddls
from .sqlite_register_layout import register_table, register_data_ddls, register_index_ddls
from . import sqlite_hierarchy as hierarchy_storage
from .sqlite_hierarchy import HIERARCHY_DDL
from . import sqlite_transaction_profile as transaction_profile
from .sqlite_query_indexes import register_query_collations
from .sqlite_read_handles import ReadHandle, reserve_owner, lifecycle
from yadinassi.db.catalog.catalog_qualifiers import normalize_field, normalize_string, validate_string, bound_number
from .sqlite_catalog_layout import (REGISTRY_DDL, MIGRATION_MARKER_DDL, build_layout, save_layout, load_layout, quote_identifier,
                                    catalog_ddl, index_ddls)
from .sqlite_typed_rows import encode_typed_columns, decode_typed_columns, decode_number, number_storage
from .sqlite_catalog_sections import (SECTION_REGISTRY_DDL, build_section_layout, save_section_layout,
                                      load_section_layout, section_ddl)
from yadinassi.db.catalog.catalog_backend import (BackendError, Capabilities, CatalogCard, CatalogDraft,
                              CatalogKey, CatalogSchema, CatalogSelection,
                              FieldSchema, Revision, CatalogComparison, CatalogPredicate,
                              CatalogOrder, CatalogScanRequest, CatalogPage, CatalogScalarRow,
                              CatalogValueRow, CatalogValuePage, TabularSectionSchema,
                              TabularRow, TabularSectionRows, CatalogSectionRecord, CatalogSectionPage, CatalogWriteOutcome,
                              _TabularSectionChanges)

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
_DEMO_SOURCE_ISSUES = {
    DEMO_PRODUCTS_PROFILE: DEMO_PRODUCTS_SOURCE_ISSUE,
    DEMO_KINDS_PROFILE: DEMO_KINDS_SOURCE_ISSUE,
    DEMO_DIRECTORIES_PROFILE: DEMO_DIRECTORIES_SOURCE_ISSUE,
}


def _source_profile_for_issues(issues):
    """Recognize exact historical grants or a persisted generic source digest."""
    if type(issues) not in (list, tuple) or len(issues) != 1:
        return None
    marker = issues[0]
    if type(marker) is not str:
        return None
    for profile, issue in ((CATALOG_FORMS_PROFILE, CATALOG_FORMS_SOURCE_ISSUE),
                           (APPLICATION_PROFILE, APPLICATION_SOURCE_ISSUE),
                           (DOCUMENT_FORMS_PROFILE, DOCUMENT_FORMS_SOURCE_ISSUE),
                           (BUSINESS_PROFILE, BUSINESS_SOURCE_ISSUE),
                           (REFERENCE_PROFILE, REFERENCE_SOURCE_ISSUE)):
        prefix = issue + ':'
        if marker.startswith(prefix):
            digest = marker[len(prefix):]
            return profile if len(digest) == 64 and all(c in '0123456789abcdef' for c in digest) else None
    return next((profile for profile, issue in _DEMO_SOURCE_ISSUES.items() if marker == issue), None)


def _interruption(error):
    return not isinstance(error, Exception) or isinstance(error, MemoryError)


def _close_document_scan(owner):
    stream = getattr(owner, '_document_scan_stream', None)
    owner._document_scan_stream = None
    owner._document_scan_lookahead = None
    if stream is not None:
        owner._scan_cursor = None
        stream.close()


def _retire_read_handle(owner):
    handle = getattr(owner, '_read_handle', None)
    if handle is not None:
        handle.invalidate()
        if getattr(owner._backend, '_read_handle', None) is handle:
            owner._backend._read_handle = None
        owner._read_handle = None


def _read_owner(value):
    owner = getattr(value, '_view', value)
    return owner if (getattr(owner, '_read_handle', None) is not None
                     and getattr(owner, '_connection', None) is not None) else None


def _close_owned_connection(owner):
    if owner._connection is None and owner._backend._active is owner:
        # An interruption may land between the successful lease's detach
        # assignments. The still-active owner exclusively owns this exact idle
        # handle until publication completes; recover it for physical retirement.
        handle = getattr(owner, '_read_handle', None) or owner._backend._read_handle
        if handle is not None:
            owner._connection = handle.connection
            owner._read_handle = handle
        else:
            owner._backend._active = None
    if owner._connection is not None:
        # Ownership stays with this owner until physical close succeeds. A
        # failed/replaced lease is never returned to the retained read slot.
        _retire_read_handle(owner)
        # A failed close makes the owner unusable but does not prove that
        # SQLite released its locks. Retain ownership until close succeeds.
        owner._closed=True; owner._scan_cursor=None
        if hasattr(owner, '_validated_sources'): owner._validated_sources.clear()
        rollback_error=None
        try:
            _close_document_scan(owner)
        except BaseException as error:
            rollback_error=error
        try:
            if owner._connection.in_transaction: owner._connection.execute('ROLLBACK')
        except BaseException as error:
            if rollback_error is None or not _interruption(rollback_error):
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
        self._read_handle=None

    @lifecycle
    def close(self):
        _close_owned_connection(self)
        # Failure before sqlite3.connect returned did not acquire a handle.
        if self._connection is None and self._backend._active is self:
            self._backend._active=None


def _boundary(function):
    @wraps(function)
    def call(*args, **kwargs):
        try:
            result = function(*args, **kwargs)
            owner = _read_owner(args[0]) if args else None
            if owner is not None and not owner._closed and not getattr(owner, '_query_language', False):
                owner._backend._check_file()
            return result
        except BaseException as error:
            owner = _read_owner(args[0]) if args else None
            if owner is not None:
                owner._read_handle.invalidate()
                if hasattr(owner, '_validated_sources'):
                    owner._validated_sources.clear()
            if isinstance(error, BackendError):
                raise
            if isinstance(error, sqlite3.Error):
                raise BackendError('storage_error') from None
            if isinstance(error, (ValueError, TypeError, KeyError, IndexError,
                                  OverflowError, RecursionError)):
                raise BackendError('integrity') from None
            raise
    return call


def _confirm_sqlite_commit(connection):
    """Return only after SQLite confirmed COMMIT; cleanup is a separate step."""
    try:
        connection.execute('COMMIT')
    except BaseException as error:
        if _interruption(error):
            raise
        raise BackendError('uncertain_commit') from None


def _revision_number(token):
    if type(token) is not str or not 1 <= len(token) <= 19 or not token.isascii() or not token.isdecimal() or token.startswith('0'):
        raise BackendError('conflict')
    result = int(token)
    if not 1 <= result < 2**63-1: raise BackendError('conflict')
    return result


def _single_catalog_scalar_schema(schema):
    return (type(schema) is CatalogSchema and schema.hierarchy == 'none'
            and not schema.tabular_sections
            and all(field.kind != 'catalog_ref' for field in schema.fields))


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


def _enum_domain(domain, database_id=None):
    # Explicit internal format16 capability, never inferred from field contents.
    from yadinassi.db.metadata.enum_storage_values import EnumValueDomain, _uuid as enum_uuid
    if type(domain) is not EnumValueDomain:
        raise BackendError('unsupported')
    try:
        owner, declarations = domain.database_id, domain.declarations
    except AttributeError:
        raise BackendError('invalid_input') from None
    enum_uuid(owner)
    if type(declarations) is not tuple or len(declarations) > 128:
        raise BackendError('invalid_input')
    seen, count = set(), 0
    for declaration in declarations:
        if type(declaration) is not tuple or len(declaration) != 2:
            raise BackendError('invalid_input')
        identity, values = declaration
        enum_uuid(identity)
        if type(values) is not tuple or len(values) > 512:
            raise BackendError('invalid_input')
        count += len(values)
        if count > 4096:
            raise BackendError('invalid_input')
        for item in (identity, *values):
            enum_uuid(item)
            if item in seen:
                raise BackendError('invalid_input')
            seen.add(item)
    if database_id is not None:
        enum_uuid(database_id)
        if database_id != domain.database_id:
            raise BackendError('invalid_input')
    return domain


def _enum_field(field, domain, database_id=None):
    domain = _enum_domain(domain, database_id)
    if (field.target_catalog_id is not None or type(field.qualifiers) is not tuple
            or field.qualifiers):
        raise BackendError('invalid_input')
    domain.empty(field.target_enum_id)
    return domain


def _fields_data(fields_schema, *, enum_domain=None):
    if enum_domain is not None:
        _enum_domain(enum_domain)
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
        if type(field.kind) is not str or field.kind not in ('string', 'number', 'boolean', 'datetime', 'catalog_ref', 'enum_ref') or type(field.qualifiers) is not tuple:
            raise BackendError('unsupported')
        if field.kind == 'enum_ref':
            domain = _enum_domain(enum_domain)
            domain.empty(field.target_enum_id)
            if field.target_catalog_id is not None:
                raise BackendError('invalid_input')
        elif field.target_enum_id is not None:
            raise BackendError('unsupported')
        q = field.qualifiers
        if field.kind == 'string' and (len(q) != 1 or type(q[0]) is not int or not 0 <= q[0] <= 65536):
            raise BackendError('invalid_input')
        if field.kind == 'number' and (len(q) != 3 or type(q[0]) is not int or type(q[1]) is not int or not 1 <= q[0] <= 38 or not 0 <= q[1] <= q[0] or type(q[2]) is not str or q[2] not in ('Any', 'Nonnegative')):
            raise BackendError('invalid_input')
        if field.kind == 'datetime' and (len(q) != 1 or type(q[0]) is not str or q[0] != 'DateTime'):
            raise BackendError('unsupported')
        if field.kind in ('boolean', 'catalog_ref', 'enum_ref') and q:
            raise BackendError('invalid_input')
        if field.kind == 'catalog_ref':
            _uuid(field.target_catalog_id)
        elif field.target_catalog_id is not None:
            raise BackendError('invalid_input')
        fields.append([identity, field.name, field.kind, list(field.qualifiers),
                       str(field.target_catalog_id) if field.target_catalog_id else None])
        if enum_domain is not None:
            fields[-1].append(str(field.target_enum_id) if field.target_enum_id is not None else None)
    return fields


def _schema_data(schema, *, enforce_serialized_limit=True, enum_domain=None):
    if type(schema) is not CatalogSchema or type(schema.tabular_sections) is not tuple:
        raise BackendError('invalid_input')
    _uuid(schema.identity)
    if type(schema.name) is not str or not schema.name or len(schema.name) > 128:
        raise BackendError('invalid_input')
    if any(type(n) is not int or not 0 <= n <= 1024 for n in (schema.code_length, schema.description_length)):
        raise BackendError('invalid_input')
    if type(schema.numbering) is not str or schema.numbering not in ('explicit', 'decimal_v1'):
        raise BackendError('invalid_input')
    if schema.numbering == 'decimal_v1' and not 1 <= schema.code_length <= 9:
        raise BackendError('invalid_input')
    if type(schema.hierarchy) is not str or schema.hierarchy not in ('none','groups_v1'): raise BackendError('invalid_input')
    fields = _fields_data(schema.fields, enum_domain=enum_domain)
    if schema.hierarchy != 'none' and any(f.name.casefold() in ('parent','isfolder','родитель','этогруппа') for f in schema.fields): raise BackendError('invalid_input')
    result = [str(schema.identity), schema.name, schema.code_length, schema.description_length, fields]
    if len(schema.tabular_sections) > _MAX_SECTIONS: raise BackendError('invalid_input')
    names = {'code', 'description', 'deletionmark', 'ref'} | ({'parent','isfolder','родитель','этогруппа'} if schema.hierarchy != 'none' else set()) | {f.name.casefold() for f in schema.fields}
    ids = {schema.identity} | {f.identity for f in schema.fields}
    sections = []
    for section in schema.tabular_sections:
        if type(section) is not TabularSectionSchema or type(section.name) is not str or not section.name or len(section.name) > 128:
            raise BackendError('invalid_input')
        identity = _uuid(section.identity)
        if section.identity in ids or section.name.casefold() in names: raise BackendError('invalid_input')
        names.add(section.name.casefold()); ids.add(section.identity)
        sections.append([identity, section.name, _fields_data(section.fields, enum_domain=enum_domain)])
    # Preserve the original five-element serialization for configurations without
    # sections, including existing stored definitions and migration fingerprints.
    if sections or schema.numbering != 'explicit' or schema.hierarchy != 'none': result.append(sections)
    if schema.numbering != 'explicit' or schema.hierarchy != 'none': result.append(['numbering_v1', schema.numbering])
    if schema.hierarchy != 'none': result.append(['hierarchy_v1',schema.hierarchy])
    if enforce_serialized_limit and len(_json(result)) > 65536: raise BackendError('invalid_input')
    return result


def _schema(raw, *, allow_numbering=False, allow_hierarchy=False, enum_domain=None):
    if type(raw) is not str or len(raw) > 65536: raise BackendError('integrity')
    data = json.loads(raw)
    if type(data) is not list or len(data) not in (5, 6, 7, 8): raise BackendError('integrity')
    def identity(value):
        if type(value) is not str: raise BackendError('integrity')
        result = UUID(value)
        if str(result) != value or not result.int: raise BackendError('integrity')
        return result
    def fields(items):
        if type(items) is not list or len(items) > 64: raise BackendError('integrity')
        if any(type(f) is not list or len(f) != (6 if enum_domain is not None else 5) or type(f[3]) is not list for f in items): raise BackendError('integrity')
        return tuple(FieldSchema(identity(f[0]), f[1], f[2], tuple(f[3]), identity(f[4]) if f[4] is not None else None, identity(f[5]) if enum_domain is not None and f[5] is not None else None) for f in items)
    sections = ()
    if len(data) >= 6:
        if type(data[5]) is not list or not (0 if len(data) >= 7 else 1) <= len(data[5]) <= _MAX_SECTIONS: raise BackendError('integrity')
        if any(type(s) is not list or len(s) != 3 for s in data[5]): raise BackendError('integrity')
        sections = tuple(TabularSectionSchema(identity(s[0]), s[1], fields(s[2])) for s in data[5])
    numbering = 'explicit'
    if len(data) >= 7:
        if not allow_numbering: raise BackendError('unsupported')
        allowed = ('explicit','decimal_v1') if len(data) == 8 else ('decimal_v1',)
        if type(data[6]) is not list or len(data[6]) != 2 or data[6][0] != 'numbering_v1' or data[6][1] not in allowed: raise BackendError('integrity')
        numbering = data[6][1]
    hierarchy = 'none'
    if len(data) == 8:
        if not allow_hierarchy: raise BackendError('unsupported')
        if data[7] != ['hierarchy_v1','groups_v1']: raise BackendError('integrity')
        hierarchy = 'groups_v1'
    result = CatalogSchema(identity(data[0]), data[1], data[2], data[3], fields(data[4]), sections, numbering, hierarchy)
    if _schema_data(result, enforce_serialized_limit=False, enum_domain=enum_domain) != data:
        raise BackendError('integrity')
    return result


def _all_fields(schema):
    return schema.fields + tuple(f for section in schema.tabular_sections for f in section.fields)


def _intent(draft, revision, values, sections, *, hierarchy=False):
    result = [str(draft.key.catalog_id), str(draft.key.record_id), draft.code,
              draft.description, draft.deletion_mark, values, revision]
    # Distinguish an explicit replacement, including an explicitly empty tuple,
    # when accounting for the complete request to a unit of work.
    if sections is not None: result.append(['tabular_sections_v1', sections])
    if draft.auto_number: result.append(['auto_number_v1', 'decimal_v1'])
    if hierarchy: result.append(['hierarchy_v1',None if draft.parent is None else str(draft.parent.record_id),draft.is_folder])
    return result


def _encode(value, field, database_id, *, enum_domain=None):
    if type(field) is not FieldSchema or type(field.kind) is not str:
        raise BackendError('invalid_input')
    if enum_domain is not None:
        _enum_domain(enum_domain, database_id)
    if field.kind == 'enum_ref':
        return _enum_field(field, enum_domain, database_id).encode(value, field.target_enum_id)
    if field.target_enum_id is not None:
        raise BackendError('unsupported')
    kind, q = field.kind, field.qualifiers
    if kind == 'string':
        if len(q) != 1:
            raise BackendError('invalid_input')
        try: validate_string(value, q[0])
        except (ValueError, TypeError): raise BackendError('invalid_input') from None
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
        try: bound_number(value)
        except (ValueError, TypeError): raise BackendError('invalid_input') from None
        # An independent context avoids the caller's precision, rounding, traps,
        # exponent limits and flags. This remains strict: no value can change.
        context = decimal.Context(prec=80, rounding=decimal.ROUND_HALF_EVEN,
            Emin=-999999, Emax=999999, capitals=1, clamp=0,
            flags=[], traps=[decimal.InvalidOperation])
        quantum = decimal.Decimal((0, (1,), -scale))
        try: quantized = context.quantize(value, quantum)
        except decimal.InvalidOperation: raise BackendError('invalid_input') from None
        if quantized != value or value.copy_abs() >= decimal.Decimal((0, (1,), digits-scale)):
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


def _decode(value, field, database_id, *, enum_domain=None):
    if type(field) is not FieldSchema or type(field.kind) is not str:
        raise BackendError('invalid_input')
    if enum_domain is not None:
        _enum_domain(enum_domain, database_id)
    if field.kind == 'enum_ref':
        return _enum_field(field, enum_domain, database_id).decode(value, field.target_enum_id)
    if field.target_enum_id is not None:
        raise BackendError('unsupported')
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
        if _encode(result, field, database_id, enum_domain=enum_domain) != value: raise BackendError('integrity')
        return result
    except (ValueError, TypeError, decimal.InvalidOperation):
        raise BackendError('integrity') from None


_DDL = (
    'CREATE TABLE database_info(singleton INTEGER PRIMARY KEY CHECK(singleton=1), database_uuid TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation>0), configuration_uuid TEXT NOT NULL, name TEXT NOT NULL, activated INTEGER NOT NULL CHECK(activated IN(0,1)), activation_issues TEXT NOT NULL)',
    'CREATE TABLE configuration_file(path TEXT PRIMARY KEY, kind TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL)',
    'CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE catalog_record(catalog_id TEXT NOT NULL REFERENCES catalog_schema(identity), record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), code TEXT NOT NULL, description TEXT NOT NULL, deletion_mark INTEGER NOT NULL CHECK(deletion_mark IN(0,1)), values_json TEXT NOT NULL, PRIMARY KEY(catalog_id,record_id), UNIQUE(catalog_id,code))',
)


_SEQUENCE_DDL = 'CREATE TABLE catalog_sequence(catalog_id TEXT PRIMARY KEY REFERENCES catalog_schema(identity), next_value INTEGER NOT NULL CHECK(next_value>0))'


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
        self._owner_lock = RLock()
        self._read_handle = None
        self._single_statement_writer = None
        self._read_admission_baseline = None
        from yadinassi.execution.prepared_source import PreparedSource
        self._prepared_source = PreparedSource()
        self._enum_domain = None
        self._file_identity = self._check_file()
        connection = self._connect()
        try:
            connection.execute('BEGIN')  # Pin schema, registry and metadata to one snapshot.
            if connection.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID:
                raise BackendError('unsupported')
            self.format_version = connection.execute('PRAGMA user_version').fetchone()[0]
            self.storage_version = (transaction_profile.base_version(connection) if self.format_version in (11, 12) else 7 if self.format_version in (13, 14, 15, 16) else self.format_version)
            if self.storage_version not in (1, 2, 3, 4, 5, 6, 7, 8, 9, 10): raise BackendError('unsupported')
            if self.format_version == 16:
                from .sqlite_inventory_enum_profile import read_source
                _, self._enum_domain, _ = read_source(connection)
            statements = list(_DDL)
            if self.storage_version >= 2:
                statements = [x for x in statements if not x.startswith('CREATE TABLE catalog_record(')]
                malformed = connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR typeof(name)!='text' OR typeof(definition)!='text' OR length(CAST(identity AS BLOB))>36 OR length(CAST(name AS BLOB))>512 OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone()
                if malformed: raise BackendError('integrity')
                count, total = connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(identity AS BLOB))+length(CAST(name AS BLOB))+length(CAST(definition AS BLOB))),0) FROM catalog_schema").fetchone()
                if not (0 if self.storage_version in (7, 8, 9, 10) else 1) <= count <= 512 or total > _MAX_CONFIG_BYTES: raise BackendError('integrity')
                rows = connection.execute('SELECT identity,name,definition FROM catalog_schema LIMIT 513').fetchall()
                if not (0 if self.storage_version in (7, 8, 9, 10) else 1) <= len(rows) <= 512: raise BackendError('integrity')
                schemas = tuple(_schema(definition, allow_numbering=self.storage_version in (4, 6, 7, 8, 9, 10), allow_hierarchy=self.storage_version == 10, enum_domain=self._enum_domain) for _,_,definition in rows)
                if any((identity,name) != (str(schema.identity),schema.name) for (identity,name,_),schema in zip(rows,schemas)):
                    raise BackendError('integrity')
                if len({schema.identity for schema in schemas}) != len(schemas): raise BackendError('integrity')
                section_count = sum(len(s.tabular_sections) for s in schemas)
                if section_count > _MAX_DATABASE_SECTIONS or (self.storage_version in (2, 5) and section_count):
                    raise BackendError('unsupported')
                if self.storage_version not in (4, 6, 7, 8, 9, 10) and any(s.numbering != 'explicit' for s in schemas):
                    raise BackendError('unsupported')
                ids = {schema.identity for schema in schemas}
                if any(f.target_catalog_id not in ids for schema in schemas for f in _all_fields(schema) if f.kind == 'catalog_ref'): raise BackendError('integrity')
                self._layout = load_layout(connection, schemas)
                if self.storage_version in (4, 6, 7, 8, 9, 10) and any(name.casefold() == 'catalog_sequence' for name in self._layout._tables.values()):
                    raise BackendError('integrity')
                self._schemas = schemas
                self._schema_snapshot = tuple(rows)
                statements.extend(REGISTRY_DDL)
                statements.append(MIGRATION_MARKER_DDL)
                statements.extend(catalog_ddl(schema, self._layout, enum_domain=self._enum_domain) for schema in schemas)
                if self.storage_version in (3, 4, 6, 7, 8, 9, 10):
                    self._section_layout = load_section_layout(connection, schemas, self._layout)
            self._document_schemas = (); self._document_snapshot = ()
            if self.storage_version in (7, 8, 9, 10):
                self._document_schemas, self._document_snapshot = load_document_schemas(connection, schemas, allow_empty=self.storage_version in (8, 9, 10), enum_domain=self._enum_domain)
                if len(schemas) + len(self._document_schemas) > 512: raise BackendError('integrity')
            self._register_schemas = (); self._register_snapshot = ()
            if self.storage_version in (8, 9, 10):
                self._register_schemas, self._register_snapshot = load_register_schemas(connection, schemas, self._document_schemas, allow_empty=self.storage_version == 10)
                if self.storage_version != 10 and (self.storage_version == 9) != any(r.periodic for r in self._register_schemas): raise BackendError('integrity')
            if self.storage_version == 10 and not any(s.hierarchy != 'none' for s in schemas): raise BackendError('integrity')
            expected = {statement.split('(')[0].split()[-1]: statement for statement in statements[:len(_DDL) - (1 if self.storage_version >= 2 else 0)]}
            if self.storage_version >= 2:
                expected.update({statement.split('(')[0].split()[-1]: statement for statement in (*REGISTRY_DDL, MIGRATION_MARKER_DDL)})
                expected.update({self._layout.table_name(schema.identity): catalog_ddl(schema, self._layout, enum_domain=self._enum_domain) for schema in schemas})
                if self.storage_version in (3, 4, 6, 7, 8, 9, 10):
                    expected.update({statement.split('(')[0].split()[-1]: statement for statement in SECTION_REGISTRY_DDL})
                    expected.update({self._section_layout.table_name(schema.identity, section.identity):
                                     section_ddl(schema, section, self._layout, self._section_layout)
                                     for schema in schemas for section in schema.tabular_sections})
            if self.storage_version in (4, 6, 7, 8, 9, 10):
                expected['catalog_sequence'] = _SEQUENCE_DDL
            if self.storage_version in (7, 8, 9, 10):
                expected.update({ddl.split('(')[0].split()[-1]: ddl
                                 for ddl in (*DOCUMENT_DDL,*document_data_ddls(
                                     self._document_schemas,self._layout,enum_domain=self._enum_domain))})
            if self.storage_version in (8, 9, 10):
                expected.update({ddl.split('(')[0].split()[-1].strip('"'): ddl
                                 for ddl in (*REGISTER_DDL,*register_data_ddls(self._register_schemas,self._layout))})
            if self.storage_version == 10:
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in HIERARCHY_DDL})
            if self.format_version in (11, 12):
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in transaction_profile.PROFILE_DDL})
            if self.format_version == 13:
                from .sqlite_posting_profile import DDL as posting_ddl
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in posting_ddl})
            if self.format_version == 14:
                from .sqlite_accumulation_profile import DDL as accumulation_ddl
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in accumulation_ddl})
            if self.format_version == 15:
                from .sqlite_inventory_profile import DDL as inventory_ddl
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in inventory_ddl})
            if self.format_version == 16:
                from .sqlite_inventory_enum_profile import DDL as enum_ddl
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in enum_ddl})
            if self.format_version == 12:
                from .sqlite_configuration_history import DDL as update_ddl
                expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in update_ddl})
            # Bound all schema text before fetching it, including unexpected objects.
            if connection.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone(): raise BackendError('unsupported')
            objects, schema_bytes = connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(name AS BLOB))+length(CAST(COALESCE(sql,'') AS BLOB))),0) FROM sqlite_master").fetchone()
            if objects > 4096 or schema_bytes > 64 * 1024 * 1024: raise BackendError('unsupported')
            actual = {name: sql for name,sql in connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7)) != 'sqlite_'")}
            if connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():
                raise BackendError('unsupported')
            movement_profile = self.format_version in (13,14,15,16)
            if movement_profile:
                # Reject old/shared-JSON or altered base tables before any
                # movement row admission touches the deterministic child names.
                if any(actual.get(name)!=ddl for name,ddl in expected.items()):
                    raise BackendError('unsupported')
            elif actual != expected: raise BackendError('unsupported')
            if self.format_version in (11, 12): transaction_profile.validate_marker(connection)
            if self.storage_version == 10:
                if connection.execute('SELECT COUNT(*) FROM catalog_hierarchy').fetchone()[0] > _MAX_ROWS * len(schemas): raise BackendError('unsupported')
                valid_ids = {str(s.identity) for s in schemas if s.hierarchy != 'none'}
                if any(c not in valid_ids for c, in connection.execute('SELECT DISTINCT catalog_id FROM catalog_hierarchy')): raise BackendError('integrity')
            if self.storage_version in (4, 6, 7, 8, 9, 10):
                self._check_sequences(connection, schemas)
            row = connection.execute('SELECT database_uuid,generation,activated,activation_issues FROM database_info WHERE singleton=1').fetchone()
            self.activated = row[2] == 1
            if type(row[3]) is not str or len(row[3]) > 65536: raise BackendError('integrity')
            issues = json.loads(row[3])
            if type(issues) is not list or len(issues) > 2048 or any(type(v) is not str or len(v) > 1024 for v in issues): raise BackendError('integrity')
            self.activation_issues = tuple(issues)
            if type(row[2]) is not int or row[2] not in (0,1) or any(type(v) is not str for v in self.activation_issues) or (self.activated and self.activation_issues and not ((self.storage_version == 6 and _source_profile_for_issues(self.activation_issues) in (*_DEMO_SOURCE_ISSUES, CATALOG_FORMS_PROFILE, APPLICATION_PROFILE)) or (self.storage_version == 7 and self.format_version == 7 and _source_profile_for_issues(self.activation_issues) in (DOCUMENT_FORMS_PROFILE, BUSINESS_PROFILE, REFERENCE_PROFILE)))): raise BackendError('integrity')
            self.database_id = UUID(row[0]); self.configuration_generation = row[1]
            if self.format_version == 12:
                from .sqlite_configuration_history import validate
                validate(connection, self)
            self.posting_configuration = None
            self.accumulation_configuration = None
            self._recorder_schemas = ()
            self._accumulation_schemas = ()
            if self.format_version == 13:
                from .sqlite_posting_profile import admit
                self.posting_configuration = admit(connection, self.database_id, self._document_schemas, validate_rows=True,
                    _prepared=self._prepared_source)
                self._recorder_schemas = self.posting_configuration.registers
            if self.format_version == 14:
                from .sqlite_accumulation_profile import admit
                self.accumulation_configuration = admit(connection, self.database_id, self._document_schemas, validate_rows=True,
                    _prepared=self._prepared_source)
                self._accumulation_schemas = self.accumulation_configuration.registers
            if self.format_version == 15:
                from .sqlite_inventory_profile import admit
                self.accumulation_configuration = admit(connection, self.database_id, self._schemas,
                    self._document_schemas, validate_rows=True, _prepared=self._prepared_source)
                self._accumulation_schemas = self.accumulation_configuration.registers
            if self.format_version == 16:
                from .sqlite_inventory_enum_profile import admit
                self.accumulation_configuration = admit(connection, self.database_id, self._schemas,
                    self._document_schemas, validate_rows=True, _prepared=self._prepared_source)
                self._accumulation_schemas = self.accumulation_configuration.registers
            structural_indexes = register_index_ddls(self._register_schemas)
            if movement_profile:
                # Dynamic tables are declared only by the authenticated
                # profile, never by introspecting unknown physical tables.
                if self.format_version == 13:
                    from .sqlite_recorder_movements import recorder_movement_ddls
                    declarations = recorder_movement_ddls(self._recorder_schemas)
                else:
                    from .sqlite_accumulation_movements import accumulation_movement_ddls
                    declarations = accumulation_movement_ddls(self._accumulation_schemas,self._layout,
                                                               enum_domain=self._enum_domain)
                for ddl in declarations:
                    if ddl.startswith('CREATE TABLE '):
                        expected[ddl.split('(')[0].split()[-1].strip('"')] = ddl
                    else: structural_indexes += (ddl,)
                if actual != expected: raise BackendError('unsupported')
            if self.format_version in (11,12,13,14,15,16):
                structural_indexes += transaction_profile.profile_index_ddls(self.storage_version,self._schemas,self._layout)
            self._storage_indexes = structural_indexes
            from .sqlite_query_indexes import read_index_bundle_ddls, admit_query_indexes
            self._query_indexes = (admit_query_indexes(connection, structural_indexes,
                read_index_bundle_ddls(self.storage_version,self._schemas,self._layout,
                                       format_version=self.format_version))
                if self.storage_version >= 2 else False)
            self._catalog_runtime_data = None
            if self.format_version == 16:
                from .sqlite_catalog_runtime_data import CatalogRuntimeData
                self._catalog_runtime_data = CatalogRuntimeData(self)
            self._sqlite_schema_version = connection.execute('PRAGMA schema_version').fetchone()[0]
            self._register_runtime_data = None
            if (self.activated and not self.activation_issues
                    and self.format_version in (8,9,10) and self._register_schemas):
                from .sqlite_register_runtime_data import RegisterRuntimeData
                self._register_runtime_data = RegisterRuntimeData(self,connection,_APPLICATION_ID,row)
            # The generic epoch descriptor must also notice DDL changes whose
            # writer deliberately restored schema_version to its old value.
            self._admission_ddl_snapshot = None
            if self.format_version != 16 and self._read_admission_cache_allowed():
                self._admission_ddl_snapshot = tuple(connection.execute(
                    'SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall())
            _uuid(self.database_id)
            if self.storage_version == 5:
                imported, catalogs, info, manifest = self._inert_source_snapshot(connection, admitting=True)
                self._inert_configuration_id = imported.config_uuid
                self._inert_manifest = manifest
            elif self.storage_version == 6:
                imported, catalogs, info, manifest = self._demo_source_snapshot(connection, admitting=True)
                self._demo_configuration_id = imported.config_uuid
                self._demo_configuration_name = imported.name
                self._demo_manifest = manifest
                active_ids = {s.identity for s in imported.catalogs}
                self._demo_form_catalog_ids = tuple(c.identity for c in catalogs
                    if c.identity in active_ids and c.default_object_form)
            elif _source_profile_for_issues(self.activation_issues) == DOCUMENT_FORMS_PROFILE:
                self._document_form_source_snapshot(connection, admitting=True)
            elif _source_profile_for_issues(self.activation_issues) in (BUSINESS_PROFILE, REFERENCE_PROFILE):
                self._business_source_snapshot(connection, admitting=True)
            elif INERT_SOURCE_ISSUE in self.activation_issues or _source_profile_for_issues(self.activation_issues) is not None:
                raise BackendError('unsupported')
        except BackendError: raise
        except (sqlite3.Error, TypeError, ValueError):
            raise BackendError('integrity') from None
        finally: connection.close()

    @staticmethod
    def _check_sequences(connection, schemas):
        expected = {str(s.identity): 10 ** s.code_length for s in schemas if s.numbering == 'decimal_v1'}
        if connection.execute("SELECT 1 FROM catalog_sequence WHERE typeof(catalog_id)!='text' OR length(CAST(catalog_id AS BLOB))!=36 OR typeof(next_value)!='integer' LIMIT 1").fetchone():
            raise BackendError('integrity')
        rows = connection.execute('SELECT catalog_id,next_value FROM catalog_sequence LIMIT 513').fetchall()
        if (len(rows) != len(expected) or any(type(c) is not str or c not in expected
                or type(n) is not int or not 1 <= n <= expected[c] for c,n in rows)
                or len({c for c,n in rows}) != len(rows)):
            raise BackendError('integrity')

    def _check_file(self):
        try:
            info = os.lstat(self.path)
            if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_nlink != 1 or info.st_size > _MAX_DATABASE_BYTES:
                raise BackendError('invalid_input')
            _private_parent(self.path)
            identity = (info.st_dev, info.st_ino)
            if getattr(self, '_file_identity', identity) != identity:
                raise BackendError('schema_changed')
            return identity
        except OSError: raise BackendError('storage_error') from None

    def _connect(self, *, _owner=None, _read_handle=False, _single_statement=False):
        self._check_file()
        connection = None
        try:
            readonly = self.read_only or _read_handle
            connection = sqlite3.connect(Path(self.path).as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, isolation_level=None, detect_types=0, timeout=0.2,
                                         check_same_thread=not (_read_handle or _single_statement))
            if _owner is not None: _owner._connection=connection
            register_query_collations(connection)
            if readonly: connection.execute('PRAGMA query_only=ON')
            connection.execute('PRAGMA foreign_keys=ON')
            connection.execute('PRAGMA trusted_schema=OFF')
            connection.execute('PRAGMA synchronous=FULL')
            if not readonly:
                page_size = connection.execute('PRAGMA page_size').fetchone()[0]
                connection.execute('PRAGMA max_page_count=%d' % (_MAX_DATABASE_BYTES // page_size))
            if connection.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
                raise BackendError('unsupported')
            if connection.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete':
                raise BackendError('unsupported')
            self._check_file()
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
    def create_inventory_enum(cls, path, configuration):
        from .sqlite_inventory_enum_profile import create
        return create(cls, path, configuration)

    @classmethod
    @_boundary
    def create_inventory(cls, path, configuration):
        from .sqlite_inventory_profile import create
        return create(cls, path, configuration)

    @classmethod
    @_boundary
    def create_main_demo(cls, path, configuration):
        from .sqlite_inventory_enum_profile import create_main_demo
        return create_main_demo(cls, path, configuration)

    @classmethod
    @_boundary
    def create_inventory_enum_application(cls, path, configuration):
        from .sqlite_inventory_enum_profile import create_application
        return create_application(cls, path, configuration)

    @classmethod
    @_boundary
    def create_inventory_application(cls, path, configuration):
        from .sqlite_inventory_profile import create_application
        return create_application(cls, path, configuration)

    @classmethod
    @_boundary
    def create_accumulation(cls, path, configuration):
        from .sqlite_accumulation_profile import create
        return create(cls, path, configuration)

    @classmethod
    @_boundary
    def create_posting(cls, path, configuration):
        from .sqlite_posting_profile import create
        return create(cls, path, configuration)

    @classmethod
    @_boundary
    def create(cls, path, configuration, *, activate=True, query_indexes=False, _source_profile=None):
        """Create only a new owned file, atomically import admitted XML and code."""
        (schemas, registers, documents, definitions, register_definitions, document_definitions, storage_version, files) = _preflight_create(configuration, activate=activate, query_indexes=query_indexes, _source_profile=_source_profile)
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
            register_query_collations(connection)
            connection.execute('PRAGMA foreign_keys=ON'); connection.execute('PRAGMA journal_mode=DELETE'); connection.execute('PRAGMA synchronous=FULL')
            connection.execute('BEGIN IMMEDIATE')
            for statement in _DDL:
                if not statement.startswith('CREATE TABLE catalog_record('): connection.execute(statement)
            for statement in (*REGISTRY_DDL, MIGRATION_MARKER_DDL): connection.execute(statement)
            if storage_version in (3, 4, 6, 7, 8, 9, 10):
                for statement in SECTION_REGISTRY_DDL: connection.execute(statement)
            if storage_version in (7, 8, 9, 10):
                for statement in DOCUMENT_DDL: connection.execute(statement)
                connection.executemany('INSERT INTO document_schema VALUES(?,?,?)', ((str(d.identity),d.name,_json(definition)) for d,definition in zip(documents,document_definitions)))
                connection.executemany('INSERT INTO document_sequence VALUES(?,1)', ((str(d.identity),) for d in documents if d.numbering == 'decimal_v1'))
            if storage_version in (8, 9, 10):
                for statement in REGISTER_DDL: connection.execute(statement)
                connection.executemany('INSERT INTO information_register_schema VALUES(?,?,?)', ((str(r.identity),r.name,_json(d)) for r,d in zip(registers,register_definitions)))
                connection.executemany('INSERT INTO information_register_sequence VALUES(?,1)', ((str(r.identity),) for r in registers))
            connection.execute('INSERT INTO database_info VALUES(1,?,1,?,?,?,?)', (str(uuid4()), _uuid(configuration.config_uuid), configuration.name, int(activate), _json(configuration.activation_issues)))
            for definition in definitions:
                connection.execute('INSERT INTO catalog_schema VALUES(?,?,?)', (definition[0], definition[1], _json(definition)))
            if storage_version in (4, 6, 7, 8, 9, 10):
                connection.execute(_SEQUENCE_DDL)
                connection.executemany('INSERT INTO catalog_sequence VALUES(?,1)',
                    ((str(s.identity),) for s in schemas if s.numbering == 'decimal_v1'))
            if storage_version == 10:
                for statement in HIERARCHY_DDL: connection.execute(statement)
            reserved_names = tuple(ddl.split('(')[0].split()[-1] for ddl in SECTION_REGISTRY_DDL) if storage_version in (3, 4, 6, 7, 8, 9, 10) else ()
            if storage_version in (4, 6, 7, 8, 9, 10): reserved_names += ('catalog_sequence',)
            if storage_version in (7, 8, 9, 10): reserved_names += tuple(ddl.split('(')[0].split()[-1] for ddl in DOCUMENT_DDL)
            if storage_version in (8, 9, 10):
                reserved_names += (*tuple(ddl.split('(')[0].split()[-1] for ddl in REGISTER_DDL),
                                   *(register_table(schema) for schema in registers))
            if storage_version == 10: reserved_names += ('catalog_hierarchy',)
            layout = build_layout(schemas, reserved_names=reserved_names)
            save_layout(connection, layout)
            for schema in schemas:
                connection.execute(catalog_ddl(schema, layout))
                for statement in index_ddls(schema, layout): connection.execute(statement)
            if storage_version in (3, 4, 6, 7, 8, 9, 10):
                sections_layout = build_section_layout(schemas, layout)
                save_section_layout(connection, sections_layout)
                for schema in schemas:
                    for section in schema.tabular_sections:
                        connection.execute(section_ddl(schema, section, layout, sections_layout))
            for statement in (*document_data_ddls(documents,layout),*register_data_ddls(registers,layout),
                              *register_index_ddls(registers)):
                connection.execute(statement)
            if query_indexes:
                from .sqlite_query_indexes import read_index_bundle_ddls, check_index_bundle_budget
                bundle=read_index_bundle_ddls(storage_version,schemas,layout,format_version=storage_version)
                check_index_bundle_budget(connection,bundle)
                for statement in bundle:
                    connection.execute(statement)
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

    @classmethod
    @_boundary
    def create_inert(cls, path, files):
        """Create a permanently non-executable archive of original source bytes."""
        from yadinassi.configuration.configuration_xml import import_inert_configuration
        return cls.create(path, import_inert_configuration(files), activate=False)

    @classmethod
    @_boundary
    def create_demo_kinds(cls, path, files):
        """Fresh, partial exact-demo profile; other source catalogs stay inert."""
        from yadinassi.configuration.configuration_xml import import_demo_kinds_configuration
        return cls.create(path, import_demo_kinds_configuration(files), _source_profile=DEMO_KINDS_PROFILE)

    @classmethod
    @_boundary
    def create_demo_directories(cls, path, files):
        """Fresh exact-demo kinds and warehouses; products remain inert."""
        from yadinassi.configuration.configuration_xml import import_demo_directories_configuration
        return cls.create(path, import_demo_directories_configuration(files),
                          _source_profile=DEMO_DIRECTORIES_PROFILE)

    @classmethod
    @_boundary
    def create_demo_products(cls, path, files):
        """Fresh exact-demo product storage with mandatory host preparation."""
        from yadinassi.configuration.configuration_xml import import_demo_products_configuration
        return cls.create(path, import_demo_products_configuration(files),
                          _source_profile=DEMO_PRODUCTS_PROFILE)

    @classmethod
    @_boundary
    def create_catalog_forms(cls, path, files):
        """Fresh explicit catalog_object_forms_v1 storage, never an archive upgrade."""
        from yadinassi.configuration.configuration_xml import import_catalog_forms_configuration
        return cls.create(path, import_catalog_forms_configuration(files),
                          _source_profile=CATALOG_FORMS_PROFILE)

    @classmethod
    @_boundary
    def create_application(cls, path, files):
        """Explicit composed source grant; old/inert import paths remain closed."""
        from yadinassi.configuration.configuration_application_profile import import_application_configuration
        return cls.create(path, import_application_configuration(files),
                          _source_profile=APPLICATION_PROFILE)

    @classmethod
    @_boundary
    def create_document_forms(cls, path, files):
        """Fresh v7 non-posting document source grant; never an implicit upgrade."""
        from yadinassi.configuration.configuration_document_profile import import_document_forms_configuration
        return cls.create(path, import_document_forms_configuration(files),
                          _source_profile=DOCUMENT_FORMS_PROFILE)

    @classmethod
    def create_business_application(cls, path, files):
        """Fresh mixed application grant; no migration or transaction admission."""
        from yadinassi.configuration.configuration_business_profile import import_business_configuration
        return cls.create(path, import_business_configuration(files), _source_profile=BUSINESS_PROFILE)

    @classmethod
    def create_reference_application(cls, path, files):
        """New owned v7 source grant; never a scalar-profile upgrade."""
        from yadinassi.configuration.configuration_reference_profile import import_reference_configuration
        return cls.create(path, import_reference_configuration(files), _source_profile=REFERENCE_PROFILE)

    def _document_form_source_snapshot(self, connection, *, admitting=False):
        from yadinassi.configuration.configuration_document_profile import import_document_forms_configuration
        from yadinassi.types.errors import BSLError
        if (self.format_version != 7 or self.storage_version != 7 or
                connection.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID or
                _source_profile_for_issues(self.activation_issues) != DOCUMENT_FORMS_PROFILE or
                connection.execute('PRAGMA user_version').fetchone()[0] != 7 or
                connection.execute('PRAGMA schema_version').fetchone()[0] != self._sqlite_schema_version):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM database_info WHERE typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))!=36 OR typeof(configuration_uuid)!='text' OR length(CAST(configuration_uuid AS BLOB))!=36 OR typeof(generation)!='integer' OR generation<1 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(activation_issues)!='text' OR length(CAST(activation_issues AS BLOB))>1024 LIMIT 1").fetchone():
            raise BackendError('integrity')
        info = connection.execute('SELECT database_uuid,configuration_uuid,generation,name,activated,activation_issues FROM database_info LIMIT 2').fetchall()
        if (len(info) != 1 or info[0][0] != str(self.database_id) or
                info[0][2] != self.configuration_generation or info[0][4] != 1 or
                info[0][5] != _json(list(self.activation_issues))):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(CAST(path AS BLOB))>1024 OR typeof(kind)!='text' OR kind NOT IN ('xml','module') OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(CAST(sha256 AS BLOB))!=64 LIMIT 1").fetchone():
            raise BackendError('integrity')
        count, total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
        if not 1 <= count <= _MAX_FILES or total > _MAX_CONFIG_BYTES:
            raise BackendError('integrity')
        files = {}; entries = []; source_entries = []
        for path, kind, content, digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file ORDER BY path'):
            if hashlib.sha256(content).hexdigest() != digest: raise BackendError('integrity')
            files[path] = content; entries.append((path, kind)); source_entries.append((path, kind, digest))
        prepared_key = ('document_forms', self.database_id, self.format_version,
            self.storage_version, self._sqlite_schema_version, tuple(info[0]), tuple(source_entries))
        imported = self._prepared_source.lookup(prepared_key)
        if imported is None:
            try: imported = import_document_forms_configuration(files)
            except (ValueError, TypeError, BSLError): raise BackendError('integrity') from None
        if (tuple((f.path, f.kind) for f in imported.files) != tuple(entries) or
                imported.activation_issues != self.activation_issues or
                (str(imported.config_uuid), imported.name) != (info[0][1], info[0][3]) or
                imported.catalogs or imported.information_registers or
                {d.identity:d for d in imported.documents} != {d.identity:d for d in self._document_schemas}):
            raise BackendError('schema_changed')
        # Export uses this validator without _begin: read persisted metadata in
        # this same snapshot rather than trusting the cached admission schemas.
        if connection.execute('SELECT COUNT(*) FROM catalog_schema').fetchone()[0] != len(self._schema_snapshot):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>65536 LIMIT 1").fetchone():
            raise BackendError('integrity')
        persisted = tuple(connection.execute('SELECT identity,name,definition FROM catalog_schema ORDER BY identity'))
        if persisted != self._schema_snapshot:
            raise BackendError('schema_changed')
        layout = load_layout(connection, self._schemas)
        sections = load_section_layout(connection, self._schemas, layout)
        if (layout._tables != self._layout._tables or layout._fields != self._layout._fields or
                sections._tables != self._section_layout._tables or sections._fields != self._section_layout._fields):
            raise BackendError('schema_changed')
        documents, rows = load_document_schemas(connection, self._schemas)
        if documents != self._document_schemas or rows != self._document_snapshot:
            raise BackendError('schema_changed')
        identity = (imported.config_uuid, imported.name, imported.activation_issues)
        if not admitting and identity != self._document_form_identity:
            raise BackendError('schema_changed')
        if admitting: self._document_form_identity = identity
        self._prepared_source.remember(prepared_key, imported)
        return imported

    def _business_source_snapshot(self, connection, *, admitting=False):
        from yadinassi.configuration.configuration_business_profile import business_configuration
        from yadinassi.types.errors import BSLError
        if (self.format_version != 7 or self.storage_version != 7 or
                connection.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID or
                _source_profile_for_issues(self.activation_issues) not in (BUSINESS_PROFILE, REFERENCE_PROFILE) or
                connection.execute('PRAGMA user_version').fetchone()[0] != 7 or
                connection.execute('PRAGMA schema_version').fetchone()[0] != self._sqlite_schema_version):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM database_info WHERE typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))!=36 OR typeof(configuration_uuid)!='text' OR length(CAST(configuration_uuid AS BLOB))!=36 OR typeof(generation)!='integer' OR generation<1 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(activation_issues)!='text' OR length(CAST(activation_issues AS BLOB))>1024 LIMIT 1").fetchone():
            raise BackendError('integrity')
        info = connection.execute('SELECT database_uuid,configuration_uuid,generation,name,activated,activation_issues FROM database_info LIMIT 2').fetchall()
        if (len(info) != 1 or info[0][0] != str(self.database_id) or
                info[0][2] != self.configuration_generation or info[0][4] != 1 or
                info[0][5] != _json(list(self.activation_issues))):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(CAST(path AS BLOB))>1024 OR typeof(kind)!='text' OR kind NOT IN ('xml','module') OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(CAST(sha256 AS BLOB))!=64 LIMIT 1").fetchone():
            raise BackendError('integrity')
        count, total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
        if not 1 <= count <= _MAX_FILES or total > _MAX_CONFIG_BYTES:
            raise BackendError('integrity')
        files = {}; entries = []; source_entries = []
        for path, kind, content, digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file ORDER BY path'):
            if hashlib.sha256(content).hexdigest() != digest: raise BackendError('integrity')
            files[path] = content; entries.append((path, kind)); source_entries.append((path, kind, digest))
        prepared_key = ('business_forms', self.database_id, self.format_version,
            self.storage_version, self._sqlite_schema_version, tuple(info[0]), tuple(source_entries))
        prepared = self._prepared_source.lookup(prepared_key)
        if prepared is None:
            try:
                if _source_profile_for_issues(self.activation_issues) == REFERENCE_PROFILE:
                    from yadinassi.configuration.configuration_reference_profile import reference_configuration
                    imported, catalogs = reference_configuration(files)
                else:
                    imported, catalogs = business_configuration(files)
            except (ValueError, TypeError, BSLError): raise BackendError('integrity') from None
        else:
            imported, catalogs = prepared
        if (tuple((f.path, f.kind) for f in imported.files) != tuple(entries) or
                imported.activation_issues != self.activation_issues or
                (str(imported.config_uuid), imported.name) != (info[0][1], info[0][3]) or
                imported.information_registers or
                {s.identity:s for s in imported.catalogs} != {s.identity:s for s in self._schemas} or
                {d.identity:d for d in imported.documents} != {d.identity:d for d in self._document_schemas}):
            raise BackendError('schema_changed')
        # Export uses this validator without _begin: read persisted metadata in
        # this same snapshot rather than trusting the cached admission schemas.
        if connection.execute('SELECT COUNT(*) FROM catalog_schema').fetchone()[0] != len(self._schema_snapshot):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>65536 LIMIT 1").fetchone():
            raise BackendError('integrity')
        persisted = tuple(connection.execute('SELECT identity,name,definition FROM catalog_schema ORDER BY identity'))
        if persisted != self._schema_snapshot:
            raise BackendError('schema_changed')
        layout = load_layout(connection, self._schemas)
        sections = load_section_layout(connection, self._schemas, layout)
        if (layout._tables != self._layout._tables or layout._fields != self._layout._fields or
                sections._tables != self._section_layout._tables or sections._fields != self._section_layout._fields):
            raise BackendError('schema_changed')
        documents, rows = load_document_schemas(connection, self._schemas)
        if documents != self._document_schemas or rows != self._document_snapshot:
            raise BackendError('schema_changed')
        identity = (imported.config_uuid, imported.name, imported.activation_issues)
        if not admitting and identity != self._business_form_identity:
            raise BackendError('schema_changed')
        if admitting: self._business_form_identity = identity
        self._check_sequences(connection, self._schemas)
        self._prepared_source.remember(prepared_key, (imported, catalogs))
        return imported, catalogs, info[0], imported.activation_issues[0].rsplit(':', 1)[1]

    @_boundary
    def catalog_write_preparation(self, catalog_id, *, expected=None):
        """Exact product source capability, never arbitrary archive activation.

        Raw transaction methods remain storage-only. CatalogObject writes use
        this policy automatically; begin_write rechecks the manifest under lock.
        """
        _uuid(catalog_id)
        if self._closed: raise BackendError('closed')
        if self.format_version == 16:
            from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
            if type(self.accumulation_configuration) is MainDemoConfiguration:
                config = self.accumulation_configuration
                # This is only policy selection, not permission to write. For an
                # already admitted catalog with no handler, avoid opening another
                # read transaction merely to discover that absence. begin_write
                # still validates current source/schema under BEGIN IMMEDIATE
                # before any row mutation. Active leases and expected-source
                # requests retain their existing validation path.
                if (self._active is None and expected is None
                        and type(config.catalog_handlers) is tuple
                        and all(type(g) is tuple and len(g) == 3 and type(g[0]) is UUID
                                for g in config.catalog_handlers)
                        and not any(g[0] == catalog_id for g in config.catalog_handlers)
                        and type(self._schemas) is tuple
                        and any(type(c) is CatalogSchema and type(c.identity) is UUID
                                and c.identity == catalog_id for c in self._schemas)):
                    return None
                return self._main_demo_write_source(catalog_id, expected=expected)
        profile = _source_profile_for_issues(self.activation_issues)
        business = profile in (BUSINESS_PROFILE, REFERENCE_PROFILE)
        if not business and (self.storage_version != 6 or profile not in (DEMO_PRODUCTS_PROFILE, CATALOG_FORMS_PROFILE, APPLICATION_PROFILE)):
            return None
        if self._active is not None: raise BackendError('busy')
        connection = self._connect()
        try:
            connection.execute('BEGIN')
            imported, catalogs, info, manifest = (self._business_source_snapshot(connection) if business else self._demo_source_snapshot(connection))
            if profile in (CATALOG_FORMS_PROFILE, APPLICATION_PROFILE, BUSINESS_PROFILE, REFERENCE_PROFILE):
                product = next((c for c in catalogs if c.identity == catalog_id), None)
                if product is None: raise BackendError('not_found')
            else:
                product = next(c for c in catalogs if c.name == 'Номенклатура')
                if catalog_id != product.identity: return None
            form = next(f for f in product.forms if product.default_object_form ==
                        'Catalog.' + product.name + '.Form.' + f.name)
            identity = ConfigurationSourceIdentity(self.database_id,
                imported.config_uuid, info[2], manifest, product.identity, form.identity)
            if expected is not None and (type(expected) is not ConfigurationSourceIdentity
                                         or expected != identity):
                raise BackendError('schema_changed')
            files = {f.path: f.content for f in imported.files}
            path = 'Catalogs/' + product.name + '/Ext/ObjectModule.bsl'
            return files[path].decode('utf-8-sig') if path in files else None
        finally:
            connection.close()

    def _defer_main_demo_write_source(self, catalog_id, policy):
        """Select a candidate only; this does not supply executable source."""
        if self.format_version != 16 or self._active is not None or self._closed:
            return False
        from types import MethodType
        from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
        from .sqlite_catalog_runtime_data import CatalogRuntimeData

        data = self._catalog_runtime_data
        config = self.accumulation_configuration
        if (type(config) is not MainDemoConfiguration or type(data) is not CatalogRuntimeData
                or data.config is not config or data.handlers is not config.catalog_handlers
                or type(catalog_id) is not UUID or type(catalog_id.int) is not int
                or catalog_id.int not in data.handler_ids):
            return False
        for name, canonical in _ORDINARY_MAIN_DEMO_WRITE_ABI:
            actual = policy if name == 'catalog_write_preparation' else getattr(self, name)
            if (type(actual) is not MethodType or actual.__self__ is not self
                    or actual.__func__ is not canonical):
                return False
        return True

    def _main_demo_write_source_on_owner(self, catalog_id, writer, operation):
        """Consume the exact source just re-admitted by this ordinary writer."""
        if (type(writer) is not _View or self._active is not writer or writer._backend is not self
                or writer._operation_id != operation or writer._catalog_data is not None
                or writer._admitted_catalogs is None or not writer._connection.in_transaction):
            raise BackendError('unsupported')
        writer._require(True)
        schema = writer._admitted_catalogs.get(catalog_id.int)
        if type(schema) is not CatalogSchema:
            raise BackendError('schema_changed')
        source = self._main_demo_policy_text(self.accumulation_configuration, catalog_id,
                                             writer_schema=schema)
        if source is None:
            raise BackendError('schema_changed')
        return source

    def _main_demo_policy_text(self, config, catalog_id, *, expected=None, writer_schema=None):
        owner = next((c for c in config.catalog_sources if c.identity == catalog_id), None)
        if owner is None: raise BackendError('not_found')
        grant = next((g for g in config.catalog_handlers if g[0] == catalog_id), None)
        if grant is None: return None
        if writer_schema is not None:
            # The locked writer copied the exact schema during admission.
            # Pin the chosen bytes to the MainDemo grant for that catalog, not
            # to a replacement in-memory grant with a matching forged digest.
            from yadinassi.configuration.demos.main_demo_source import SOURCE_SHA256
            path = 'Catalogs/' + writer_schema.name + '/Ext/ObjectModule.bsl'
            if (type(grant[1]) is not str or grant[1] != path or type(grant[2]) is not str
                    or grant[2] != SOURCE_SHA256.get(path)):
                raise BackendError('schema_changed')
        form = next(f for f in owner.forms if owner.default_object_form ==
                    'Catalog.' + owner.name + '.Form.' + f.name)
        identity = ConfigurationSourceIdentity(self.database_id, config.identity,
            self.configuration_generation, config.source_digest, owner.identity, form.identity)
        if expected is not None and (type(expected) is not ConfigurationSourceIdentity or expected != identity):
            raise BackendError('schema_changed')
        raw = dict(config.files)[grant[1]]
        if hashlib.sha256(raw).hexdigest() != grant[2]:
            raise BackendError('integrity')
        return raw.decode('utf-8-sig')

    def _main_demo_source_snapshot(self, connection):
        from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration, PROFILE, _same
        from .sqlite_inventory_enum_profile import read_source
        owner = self._active
        handle = self._read_handle
        if (type(owner) is _View and owner._connection is connection
                and owner._operation_id is None and handle is not None
                and owner._read_handle is handle and handle.connection is connection
                and handle._pending_admission is not None):
            owner._require()
            if not _same(handle._pending_admission, self._read_admission_descriptor()):
                raise BackendError('schema_changed')
            # Reuse only this explicit connection's already admitted snapshot.
            # No active writer, foreign connection or unregistered lease grant.
            config = self.accumulation_configuration
            if type(config) is not MainDemoConfiguration or config.profile != PROFILE:
                raise BackendError('schema_changed')
            return config
        config, domain, _ = read_source(connection, _prepared=self._prepared_source)
        if (type(config) is not MainDemoConfiguration or config.profile != PROFILE
                or domain.database_id != self.database_id
                or not _same(config, self.accumulation_configuration)):
            raise BackendError('schema_changed')
        return config

    def _main_demo_write_source(self, catalog_id, *, expected=None):
        lease = None
        if self._active is not None:
            from yadinassi.db.database_transactions import current, require_registered_query_lease
            if current(self) is None: raise BackendError('busy')
            lease = self.begin_read()
            try:
                require_registered_query_lease(self, lease)
                connection = lease._connection
            except BaseException:
                lease.close()
                raise
        else:
            connection = self._connect()
        try:
            if lease is None: connection.execute('BEGIN')
            config = self._main_demo_source_snapshot(connection)
            if lease is not None: require_registered_query_lease(self, lease)
            return self._main_demo_policy_text(config, catalog_id, expected=expected)
        finally:
            if lease is not None: lease.close()
            else: connection.close()

    def _demo_profile(self):
        profile = _source_profile_for_issues(self.activation_issues)
        if profile is None: raise BackendError('schema_changed')
        return profile

    @_boundary
    def active_form_catalogs(self):
        """Host capability inventory, not arbitrary stored form execution."""
        if self._closed: raise BackendError('closed')
        from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
        if self.format_version == 16 and type(self.accumulation_configuration) is MainDemoConfiguration:
            view = self.begin_read()
            try:
                config = self._main_demo_source_snapshot(view._connection)
                return tuple(c.identity for c in config.catalog_sources if c.default_object_form)
            finally:
                view.close()
        # This inventory authorizes only the historical imported-form adapter.
        # Generic object forms require the explicit configuration-form host.
        if self.storage_version != 6 or self._demo_profile() in (CATALOG_FORMS_PROFILE, APPLICATION_PROFILE): return ()
        view = self.begin_read()
        try: return self._demo_form_catalog_ids
        finally: view.close()

    def _demo_source_snapshot(self, connection, *, admitting=False):
        from yadinassi.configuration.configuration_xml import _demo_configuration
        if self.storage_version != 6: raise BackendError('unsupported')
        if (connection.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID
                or connection.execute('PRAGMA user_version').fetchone()[0] != 6
                or connection.execute('PRAGMA schema_version').fetchone()[0] != self._sqlite_schema_version):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM database_info WHERE typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))!=36 OR typeof(configuration_uuid)!='text' OR length(CAST(configuration_uuid AS BLOB))!=36 OR typeof(generation)!='integer' OR generation<1 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(activation_issues)!='text' OR length(CAST(activation_issues AS BLOB))>1024 LIMIT 1").fetchone():
            raise BackendError('integrity')
        rows = connection.execute('SELECT database_uuid,configuration_uuid,generation,name,activated,activation_issues FROM database_info LIMIT 2').fetchall()
        if len(rows) != 1: raise BackendError('integrity')
        info = rows[0]
        if (info[0] != str(self.database_id) or type(info[2]) is not int
                or info[2] != self.configuration_generation): raise BackendError('schema_changed')
        if (type(info[4]) is not int or info[4] != 1
                or info[5] != _json(list(self.activation_issues))): raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(CAST(path AS BLOB))>1024 OR typeof(kind)!='text' OR kind NOT IN ('xml','module') OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(CAST(sha256 AS BLOB))!=64 LIMIT 1").fetchone():
            raise BackendError('integrity')
        count, total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
        valid_count = (1 <= count <= _MAX_FILES if self._demo_profile() in (CATALOG_FORMS_PROFILE, APPLICATION_PROFILE) else count == 19)
        if not valid_count or total > _MAX_CONFIG_BYTES: raise BackendError('schema_changed')
        files = {}; entries = []
        for path, kind, content, digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file ORDER BY path'):
            if hashlib.sha256(content).hexdigest() != digest: raise BackendError('integrity')
            files[path] = content
            entries.append([path, kind, len(content), digest])
        prepared_key = ('catalog_forms', self.database_id, self.format_version,
            self.storage_version, self._sqlite_schema_version, tuple(info),
            self._demo_profile(), tuple(tuple(entry) for entry in entries))
        prepared = self._prepared_source.lookup(prepared_key)
        if prepared is None:
            try: imported, catalogs = _demo_configuration(files, self._demo_profile())
            except ValueError: raise BackendError('schema_changed') from None
        else:
            imported, catalogs = prepared
        if (info[1], info[3]) != (str(imported.config_uuid), imported.name): raise BackendError('schema_changed')
        if imported.activation_issues != self.activation_issues: raise BackendError('schema_changed')
        if tuple((f.path, f.kind) for f in imported.files) != tuple((e[0], e[1]) for e in entries): raise BackendError('integrity')
        expected = {(str(c.identity), c.name, _json(_schema_data(c))) for c in imported.catalogs}
        if connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))>36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>4096 LIMIT 1").fetchone():
            raise BackendError('integrity')
        rows = connection.execute('SELECT identity,name,definition FROM catalog_schema LIMIT ?', (len(expected) + 1,)).fetchall()
        if len(rows) != len(expected) or set(rows) != expected: raise BackendError('schema_changed')
        manifest = hashlib.sha256(_json([self._demo_profile(), entries]).encode('utf-8')).hexdigest()
        if not admitting and (imported.config_uuid != self._demo_configuration_id or manifest != self._demo_manifest):
            raise BackendError('schema_changed')
        self._prepared_source.remember(prepared_key, (imported, catalogs))
        return imported, catalogs, info, manifest

    def _inert_source_snapshot(self, connection, *, admitting=False):
        from yadinassi.configuration.configuration_xml import _inert_configuration
        if self.storage_version != 5: raise BackendError('unsupported')
        if (connection.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID
                or connection.execute('PRAGMA user_version').fetchone()[0] != 5
                or connection.execute('PRAGMA schema_version').fetchone()[0] != self._sqlite_schema_version):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM database_info WHERE typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))!=36 OR typeof(configuration_uuid)!='text' OR length(CAST(configuration_uuid AS BLOB))!=36 OR typeof(generation)!='integer' OR generation<1 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(activation_issues)!='text' OR length(CAST(activation_issues AS BLOB))>1024 LIMIT 1").fetchone():
            raise BackendError('integrity')
        info = connection.execute('SELECT database_uuid,configuration_uuid,generation,name,activated,activation_issues FROM database_info WHERE singleton=1').fetchone()
        if info is None or info[4] != 0 or info[5] != _json([INERT_SOURCE_ISSUE]):
            raise BackendError('integrity')
        database_id, configuration_id = UUID(info[0]), UUID(info[1])
        if not database_id.int or not configuration_id.int or str(database_id) != info[0] or str(configuration_id) != info[1]:
            raise BackendError('integrity')
        if (database_id, info[2]) != (self.database_id, self.configuration_generation):
            raise BackendError('schema_changed')
        if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(CAST(path AS BLOB))>1024 OR typeof(kind)!='text' OR kind NOT IN ('xml','module') OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(CAST(sha256 AS BLOB))!=64 LIMIT 1").fetchone():
            raise BackendError('integrity')
        count, total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
        if not 1 <= count <= _MAX_FILES or total > _MAX_CONFIG_BYTES: raise BackendError('integrity')
        files = {}; entries = []
        for path, kind, content, digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file ORDER BY path'):
            if hashlib.sha256(content).hexdigest() != digest: raise BackendError('integrity')
            files[path] = content
            entries.append([path, kind, len(content), digest])
        imported, catalogs = _inert_configuration(files)
        if tuple((f.path, f.kind) for f in imported.files) != tuple((e[0], e[1]) for e in entries):
            raise BackendError('integrity')
        if (configuration_id, info[3]) != (imported.config_uuid, imported.name):
            raise BackendError('integrity')
        # Stored schemas are identity-only stubs, not inferred runnable semantics.
        expected = {(str(c.identity), c.name, _json(_schema_data(c))) for c in imported.catalogs}
        if connection.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))>36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>4096 LIMIT 1").fetchone():
            raise BackendError('integrity')
        rows = connection.execute('SELECT identity,name,definition FROM catalog_schema LIMIT 513').fetchall()
        if len(rows) != len(expected) or set(rows) != expected: raise BackendError('integrity')
        layout = load_layout(connection, imported.catalogs)
        if layout._tables != self._layout._tables or layout._fields != self._layout._fields:
            raise BackendError('schema_changed')
        manifest = hashlib.sha256(_json(['inert_sources_v1', entries]).encode('utf-8')).hexdigest()
        if not admitting and (configuration_id != self._inert_configuration_id or manifest != self._inert_manifest):
            raise BackendError('schema_changed')
        return imported, catalogs, info, manifest

    @_boundary
    def read_catalog_editor_source(self, catalog_id, *, expected=None):
        """Form and optional write policy from one freshly verified SQL snapshot."""
        return self._read_form_source(catalog_id, expected=expected, include_policy=True)

    @_boundary
    def read_form_source(self, catalog_id, *, expected=None):
        return self._read_form_source(catalog_id, expected=expected)

    def _read_form_source(self, catalog_id, *, expected=None, include_policy=False):
        """Read only the declared DefaultObjectForm from one verified snapshot.

        The returned bytes are not executable authority. No transaction survives
        this call; a later real Write needs its own atomic generation condition.
        """
        _uuid(catalog_id)
        if self._closed: raise BackendError('closed')
        business = _source_profile_for_issues(self.activation_issues) in (BUSINESS_PROFILE, REFERENCE_PROFILE)
        from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
        main_demo = self.format_version == 16 and type(self.accumulation_configuration) is MainDemoConfiguration
        if self.storage_version not in (5, 6) and not business and not main_demo: raise BackendError('unsupported')
        if self._active is not None: raise BackendError('busy')
        if expected is not None:
            if type(expected) is not ConfigurationSourceIdentity: raise BackendError('invalid_input')
            for value in (expected.database_id, expected.configuration_id, expected.catalog_id, expected.form_id): _uuid(value)
            if (type(expected.generation) is not int or not 1 <= expected.generation < 2**63
                    or type(expected.manifest_sha256) is not str or len(expected.manifest_sha256) != 64
                    or any(c not in '0123456789abcdef' for c in expected.manifest_sha256)):
                raise BackendError('invalid_input')
        connection = self._connect()
        try:
            connection.execute('BEGIN')
            if main_demo:
                config = self._main_demo_source_snapshot(connection)
                catalog = next((c for c in config.catalog_sources if c.identity == catalog_id), None)
                if catalog is None: raise BackendError('not_found')
                form = next((f for f in catalog.forms if catalog.default_object_form ==
                            'Catalog.'+catalog.name+'.Form.'+f.name), None)
                if form is None: raise BackendError('not_found')
                identity = ConfigurationSourceIdentity(self.database_id, config.identity,
                    self.configuration_generation, config.source_digest, catalog.identity, form.identity)
                if expected is not None and expected != identity: raise BackendError('schema_changed')
                files = dict(config.files)
                record = CatalogFormSource(identity, catalog.name, form.name, catalog.default_object_form,
                    catalog.path, form.path, form.definition_path, form.module_path,
                    files['Configuration.xml'], files[catalog.path], files[form.path],
                    files[form.definition_path], files.get(form.module_path,b''), form.module_path in files)
                if not include_policy:
                    return record
                grant = next((g for g in config.catalog_handlers if g[0] == catalog_id), None)
                policy = None
                if grant is not None:
                    raw = files[grant[1]]
                    if hashlib.sha256(raw).hexdigest() != grant[2]:
                        raise BackendError('integrity')
                    policy = raw.decode('utf-8-sig')
                return record, policy
            imported, catalogs, info, manifest = (self._business_source_snapshot(connection) if business else
                self._demo_source_snapshot(connection) if self.storage_version == 6 else self._inert_source_snapshot(connection))
            if self.storage_version == 6 and catalog_id not in {s.identity for s in imported.catalogs}: raise BackendError('unsupported')
            catalog = next((c for c in catalogs if c.identity == catalog_id), None)
            if catalog is None: raise BackendError('not_found')
            form = next((f for f in catalog.forms if catalog.default_object_form == 'Catalog.'+catalog.name+'.Form.'+f.name), None)
            if form is None: raise BackendError('not_found')
            identity = ConfigurationSourceIdentity(self.database_id, imported.config_uuid, info[2], manifest, catalog.identity, form.identity)
            if expected is not None and expected != identity: raise BackendError('schema_changed')
            files = {f.path: f.content for f in imported.files}
            record = CatalogFormSource(identity, catalog.name, form.name, catalog.default_object_form,
                catalog.path, form.path, form.definition_path, form.module_path,
                files['Configuration.xml'], files[catalog.path], files[form.path],
                files[form.definition_path], files.get(form.module_path, b''), form.module_path in files)
            if not include_policy:
                return record
            profile = _source_profile_for_issues(self.activation_issues)
            policy = None
            if business or (self.storage_version == 6 and profile in (
                    DEMO_PRODUCTS_PROFILE, CATALOG_FORMS_PROFILE, APPLICATION_PROFILE)):
                if profile != DEMO_PRODUCTS_PROFILE or catalog.name == 'Номенклатура':
                    path = 'Catalogs/' + catalog.name + '/Ext/ObjectModule.bsl'
                    policy = files[path].decode('utf-8-sig') if path in files else None
            return record, policy
        finally: connection.close()

    @_boundary
    def capabilities(self):
        active = self.activated and self.storage_version != 5
        return Capabilities(active, active and not self.read_only, active and not self.read_only, active and not self.read_only,
                            catalog_tabular_sections=active and (self.storage_version in (3, 4, 7, 8, 9, 10)
                                or (self.storage_version == 6 and self._demo_profile() in (DEMO_PRODUCTS_PROFILE, CATALOG_FORMS_PROFILE, APPLICATION_PROFILE))),
                            catalog_write_outcomes=active and self.storage_version in (4, 6, 7, 8, 9, 10),
                            document_read=active and self.storage_version in (7, 8, 9, 10),
                            document_create=active and self.storage_version in (7, 8, 9, 10) and not self.read_only,
                            document_update=active and self.storage_version in (7, 8, 9, 10) and not self.read_only,
                            document_tabular_sections=active and self.storage_version in (7, 8, 9, 10),
                            register_read=active and self.storage_version in (8, 9, 10),
                            register_write=active and self.storage_version in (8, 9, 10) and not self.read_only)

    @_boundary
    def launch_snapshot(self):
        """Detached exact-source UI admission under one owned read lease."""
        from .sqlite_launch import launch_snapshot
        return launch_snapshot(self)

    @_boundary
    def begin_read(self):
        from yadinassi.db.database_transactions import current
        transaction = current(self)
        return transaction.read_lease() if transaction is not None else self._begin(None)
    @_boundary
    def begin_write(self, operation_id):
        if self.read_only: raise BackendError('unsupported')
        _uuid(operation_id)
        return self._begin(operation_id)

    @_boundary
    def read_document_posted(self, key):
        if self.format_version not in (13, 14, 15, 16): raise BackendError('unsupported')
        from .sqlite_document_posting_state import read_posted
        # As with ordinary format-16 catalog data, use the opened binding.
        # This host scalar read grants no source, posting or query authority.
        if self.format_version == 16 and self._catalog_runtime_data is not None:
            from yadinassi.db.database_transactions import current
            if current(self) is None:
                return self._read_document_posted_detached(key)
        view = self.begin_read()
        try: return read_posted(view._connection, self.database_id, key)
        finally: view.close()

    def _read_document_posted_detached(self,key,*,header=None):
        from .sqlite_document_posting_state import read_posted_statement
        from .sqlite_single_statement import run

        def point(connection):
            value = read_posted_statement(connection,self.database_id,key,header=header)
            if header is not None: self._check_file()
            return value
        return run(self,point)

    @_boundary
    def _read_document_posted_scalar(self,schema,key,generation):
        from yadinassi.db.database_transactions import forbid_transfer
        from yadinassi.db.document.document_backend import DocumentKey
        from .sqlite_catalog_runtime_data import CatalogRuntimeData

        forbid_transfer(self)
        data = self._catalog_runtime_data
        if self.format_version!=16 or type(data) is not CatalogRuntimeData:
            raise BackendError('unsupported')
        if type(key) is not DocumentKey: raise BackendError('invalid_input')
        _uuid(key.database_id); _uuid(key.document_id); _uuid(key.record_id,empty=True)
        if (type(generation) is not int or (key.database_id,generation)!=data.identity
                or (self.database_id,self.configuration_generation)!=data.identity):
            raise BackendError('schema_changed')
        header = data.posted_document(self,schema,key.document_id)
        return self._read_document_posted_detached(key,header=(generation,*header))

    @_boundary
    def read_recorder(self, register_id, key):
        if self.format_version != 13: raise BackendError('unsupported')
        from .sqlite_transactions import _recorder_port
        view = self.begin_read()
        try: return _recorder_port(view).read(register_id, key)
        finally: view.close()

    @_boundary
    def read_accumulation(self, register_id, key):
        if self.format_version not in (14, 15, 16): raise BackendError('unsupported')
        from .sqlite_transactions import _accumulation_port
        view = self.begin_read()
        try: return _accumulation_port(view).read(register_id, key)
        finally: view.close()

    @_boundary
    def begin_unit_of_work(self, operation_id):
        from .sqlite_transactions import UnitOfWork
        if self.format_version not in (11, 12, 13, 14, 15, 16): raise BackendError('unsupported')
        view = self.begin_write(operation_id)
        try: return UnitOfWork(view)
        except BaseException:
            view.close(); raise

    @_boundary
    def begin_query_read(self, *, query_language=False):
        if not query_language:
            return self._document_view(None)
        from yadinassi.db.database_transactions import current
        if current(self) is not None:
            return self._document_view(None)
        view = self._begin_query_language_read()
        try:
            return DocumentView(view)
        except BaseException:
            view.close()
            raise

    @lifecycle
    def _begin_query_language_read(self):
        """Borrow a readonly connection without object admission or a new transaction."""
        if self.storage_version == 5 or not self.activated: raise BackendError('unsupported')
        pending = _PendingConnection(self)
        reserve_owner(self, pending)
        try:
            self._check_file()
            handle = self._read_handle
            if handle is None:
                connection = self._connect(_owner=pending, _read_handle=True)
                handle = ReadHandle(connection)
                pending._read_handle = self._read_handle = handle
            else:
                connection = handle.connection
                if connection.in_transaction: raise BackendError('busy')
            view = _View(self, connection, None, query_language=True)
            view._read_handle = handle
            self._active = view
            return view
        except BaseException:
            pending.close()
            raise

    @_boundary
    def begin_document_read(self):
        if self.storage_version not in (7, 8, 9, 10): raise BackendError('unsupported')
        return self._document_view(None)

    @_boundary
    def begin_document_write(self, operation_id):
        if self.read_only or self.storage_version not in (7, 8, 9, 10): raise BackendError('unsupported')
        _uuid(operation_id)
        return self._document_view(operation_id)

    def _document_view(self, operation_id):
        view = self.begin_read() if operation_id is None else self._begin(operation_id)
        try: return DocumentView(view)
        except BaseException as error:
            # A wrapper never admitted successfully; retain the original
            # physical-cleanup/poisoned-owner contract, not normal lease reuse.
            _retire_read_handle(view)
            try: view.close()
            except BaseException as cleanup_error:
                if _interruption(cleanup_error) and not _interruption(error): raise
            raise

    @_boundary
    def begin_register_read(self):
        if self.storage_version not in (8, 9, 10): raise BackendError('unsupported')
        return self._register_view(None)

    @_boundary
    def begin_register_write(self, operation_id):
        if self.read_only or self.storage_version not in (8, 9, 10): raise BackendError('unsupported')
        _uuid(operation_id)
        return self._register_view(operation_id)

    @_boundary
    def _begin_register_data(self,schema,database,generation,operation_id=None):
        from .sqlite_register_runtime_data import RegisterRuntimeData
        from yadinassi.db.database_transactions import forbid_transfer
        data = self._register_runtime_data
        if type(data) is not RegisterRuntimeData: raise BackendError('unsupported')
        forbid_transfer(self)
        if operation_id is not None:
            if self.read_only: raise BackendError('unsupported')
            _uuid(operation_id)
        descriptor = data.descriptor(self,schema,database,generation)
        return self._register_view(operation_id,descriptor=descriptor)

    def _register_view(self, operation_id, *, descriptor=None):
        if descriptor is None:
            view = self.begin_read() if operation_id is None else self._begin(operation_id)
        else:
            view = self._begin(operation_id,_register_descriptor=descriptor)
        try:
            return RegisterView(view) if descriptor is None else RegisterView(view,runtime_schema=descriptor.schema)
        except BaseException as error:
            # A wrapper never admitted successfully; retain the original
            # physical-cleanup/poisoned-owner contract, not normal lease reuse.
            _retire_read_handle(view)
            try: view.close()
            except BaseException as cleanup:
                if _interruption(cleanup) and not _interruption(error): raise
            raise

    def _check_catalog_manifest(self, connection):
        # Compare the same exact persisted triples in one bounded statement.
        # Check SQL storage types/size before copying a field into Python;
        # do not filter bad rows away or decode/reconstruct their definitions.
        remaining = set(self._schema_snapshot)
        rows = connection.execute(
            "SELECT CASE WHEN typeof(identity)='text' AND length(CAST(identity AS BLOB))<=36 THEN identity END,"
            "CASE WHEN typeof(name)='text' AND length(CAST(name AS BLOB))<=512 THEN name END,"
            "CASE WHEN typeof(definition)='text' AND length(CAST(definition AS BLOB))<=262144 THEN definition END "
            "FROM catalog_schema LIMIT ?", (len(self._schema_snapshot) + 1,))
        try:
            for row in rows:
                if row not in remaining: raise BackendError('schema_changed')
                remaining.remove(row)
        finally:
            rows.close()
        if remaining: raise BackendError('schema_changed')

    def _validate_transaction_admission(self, connection):
        if self.format_version != 16 and self._read_admission_cache_allowed():
            identity = connection.execute(
                'SELECT database_uuid,generation,activated,activation_issues FROM database_info WHERE singleton=1').fetchone()
            if identity != (str(self.database_id), self.configuration_generation,
                            int(self.activated), _json(list(self.activation_issues))):
                raise BackendError('schema_changed')
            if tuple(connection.execute(
                    'SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').fetchall()) != self._admission_ddl_snapshot:
                raise BackendError('schema_changed')
        if self.format_version != 16 and (
                connection.execute('PRAGMA user_version').fetchone()[0] != self.format_version or
                connection.execute('PRAGMA schema_version').fetchone()[0] != self._sqlite_schema_version):
            raise BackendError('schema_changed')
        if self.format_version in (11, 12) and transaction_profile.base_version(connection) != self.storage_version: raise BackendError('schema_changed')
        if self.format_version == 16:
            from .sqlite_inventory_enum_profile import read_source
            enum_source, validated_maps = read_source(
                connection, _prepared=self._prepared_source, _with_layout=True,
                _expected_versions=(self.format_version, self._sqlite_schema_version))
            config, domain, _ = enum_source
            if (config != self.accumulation_configuration or domain != self._enum_domain
                    or config.catalogs != self._schemas):
                raise BackendError('schema_changed')
        if self.storage_version >= 2:
            self._check_catalog_manifest(connection)
            # Format16 source admission just validated these maps on this
            # same transaction and exact schemas. These freshly loaded map
            # objects are not retained; readonly format16 handles separately
            # capture a detached admission descriptor after all checks pass.
            layout = validated_maps[0] if self.format_version == 16 else load_layout(connection, self._schemas)
            if layout._tables != self._layout._tables or layout._fields != self._layout._fields: raise BackendError('schema_changed')
            if self.storage_version in (3, 4, 6, 7, 8, 9, 10):
                section_layout = validated_maps[1] if self.format_version == 16 else load_section_layout(connection, self._schemas, layout)
                if section_layout._tables != self._section_layout._tables or section_layout._fields != self._section_layout._fields:
                    raise BackendError('schema_changed')
        if self.storage_version in (4, 6, 7, 8, 9, 10):
            self._check_sequences(connection, self._schemas)
        if self.storage_version in (7, 8, 9, 10):
            documents, rows = load_document_schemas(connection, self._schemas, allow_empty=self.storage_version in (8, 9, 10), enum_domain=self._enum_domain)
            if rows != self._document_snapshot or documents != self._document_schemas: raise BackendError('schema_changed')
        if self.storage_version in (8, 9, 10):
            registers, rows = load_register_schemas(connection, self._schemas, self._document_schemas, allow_empty=self.storage_version == 10)
            if rows != self._register_snapshot or registers != self._register_schemas: raise BackendError('schema_changed')
        if _source_profile_for_issues(self.activation_issues) == DOCUMENT_FORMS_PROFILE:
            self._document_form_source_snapshot(connection)
        elif _source_profile_for_issues(self.activation_issues) in (BUSINESS_PROFILE, REFERENCE_PROFILE):
            self._business_source_snapshot(connection)
        if self.storage_version == 6:
            self._demo_source_snapshot(connection)
        if self.format_version == 13:
            from .sqlite_posting_profile import admit
            if admit(connection, self.database_id, self._document_schemas,
                     _prepared=self._prepared_source) != self.posting_configuration:
                raise BackendError('schema_changed')
        if self.format_version == 14:
            from .sqlite_accumulation_profile import admit
            if admit(connection, self.database_id, self._document_schemas,
                     _prepared=self._prepared_source) != self.accumulation_configuration:
                raise BackendError('schema_changed')
        if self.format_version == 15:
            from .sqlite_inventory_profile import admit
            if admit(connection, self.database_id, self._schemas, self._document_schemas,
                     _prepared=self._prepared_source) != self.accumulation_configuration:
                raise BackendError('schema_changed')
        if self.format_version == 16:
            from .sqlite_inventory_enum_profile import _admit_source
            if _admit_source(connection, self.database_id, self._schemas, self._document_schemas,
                             enum_source, _prepared=self._prepared_source) != self.accumulation_configuration:
                raise BackendError('schema_changed')
            return config.catalogs

    def _read_admission_cache_allowed(self):
        # Source-bearing profiles require their own complete descriptor. Generic
        # migrated catalogs have no stored-code execution grant to transfer.
        return (self.format_version == 16 or
                (self.storage_version in (2, 3, 4)
                 and self.format_version in (2, 3, 4, 11)
                 and not self.activation_issues))

    def _read_admission_descriptor(self):
        # Detached source/schema/layout values, not a grant for a newly loaded
        # configuration and not a proof of catalog/document row validity.
        return (self.database_id, self.format_version, self.storage_version,
                self._sqlite_schema_version, self.activation_issues,
                self.configuration_generation, self.accumulation_configuration,
                self._enum_domain, self._schemas, self._schema_snapshot,
                self._document_schemas, self._document_snapshot,
                self._register_schemas, self._register_snapshot,
                tuple(self._layout._tables.items()), tuple(self._layout._fields.items()),
                None if not hasattr(self, '_section_layout') else tuple(self._section_layout._tables.items()),
                None if not hasattr(self, '_section_layout') else tuple(self._section_layout._fields.items()),
                self._admission_ddl_snapshot)

    @_boundary
    def _begin_catalog_data(self, catalog_id, operation_id=None):
        _uuid(catalog_id)
        if self.format_version != 16 or self._catalog_runtime_data is None:
            raise BackendError('unsupported')
        if operation_id is not None:
            _uuid(operation_id)
            if self.read_only or not self._catalog_runtime_data.allows_write(self, catalog_id):
                raise BackendError('unsupported')
        return self._begin(operation_id, _catalog_data=True)

    def _catalog_scalar_codec(self, schema, key, generation, operation_id=None):
        # This is a detached codec over the already opened descriptor, not a
        # transaction or admitted view. Its selected schema has no sections,
        # hierarchy, or fields requiring a second database operation.
        data = self._catalog_runtime_data
        if self.format_version != 16 or data is None or not _single_catalog_scalar_schema(schema):
            raise BackendError('unsupported')
        admitted = data.catalog(schema.identity)
        if admitted != schema or data.identity != (key.database_id, generation):
            raise BackendError('schema_changed')
        if operation_id is not None and (self.read_only or not data.allows_write(self, schema.identity)):
            raise BackendError('unsupported')
        codec = _View(self, None, operation_id, admitted_identity=data.identity, catalog_data=data)
        codec._key(key)
        if key.catalog_id != schema.identity:
            raise BackendError('invalid_input')
        return codec, admitted

    @_boundary
    def _read_catalog_scalar(self, schema, key, generation):
        from .sqlite_single_statement import fetch_all, run

        codec, schema = self._catalog_scalar_codec(schema, key, generation)
        table, columns, _, _ = codec._source(schema)
        sql = 'SELECT %s FROM %s WHERE record_id=? LIMIT 2' % (columns, table)
        def read(connection):
            rows = fetch_all(connection, sql, (str(key.record_id),))
            if len(rows) > 1:
                raise BackendError('integrity')
            result = None if not rows else codec._card(key.catalog_id, rows[0], schema=schema, sections=())
            self._check_file()
            return result
        return run(self, read)

    @_boundary
    def _update_catalog_scalar(self, draft, expected, schema, generation, operation_id,
                               *, pending, accept):
        from .sqlite_catalog_runtime_data import authorize_write
        from .sqlite_single_statement import execute_write, run

        _uuid(operation_id)
        codec, schema = self._catalog_scalar_codec(schema, draft.key, generation, operation_id)
        draft, values, schema = codec._draft(draft)
        if draft.auto_number or draft.tabular_sections is not None:
            raise BackendError('invalid_input')
        revision = codec._expected_revision(draft, expected)
        sql, parameters = codec._catalog_update_statement(draft, values, schema, revision,
                                                          require_unique=True)
        outcome = CatalogWriteOutcome(
            Revision(codec.database_id, generation, schema.identity, draft.key.record_id, str(revision+1)),
            draft.code)

        def update(connection):
            pending(True)
            try:
                count = execute_write(connection, sql, parameters)
            except sqlite3.IntegrityError:
                pending(False)  # Statement rolled back; a conflict can be corrected.
                raise BackendError('duplicate_code') from None
            except BaseException as error:
                if _interruption(error):
                    raise
                raise BackendError('uncertain_commit') from None
            if count == 0:
                pending(False)
                raise BackendError('conflict')
            if count != 1:
                raise BackendError('uncertain_commit')
            try:
                self._check_file()
            except BackendError:
                raise BackendError('uncertain_commit') from None
            # Confirm the object before connection cleanup, which can still
            # report an independent failure without making this write unknown.
            accept(outcome, draft)
        run(self, update, write=True, authorizer=authorize_write)

    @lifecycle
    def _begin(self, operation_id, *, _catalog_data=False, _register_descriptor=None):
        if self._closed: raise BackendError('closed')
        if self.storage_version == 5 or not self.activated: raise BackendError('unsupported')
        if self._active is not None: raise BackendError('busy')
        pending = _PendingConnection(self)
        reserve_owner(self, pending)
        try:
            self._check_file()
            if operation_id is not None and self._read_handle is not None:
                # Even a failed/uncertain writer must never reuse prior facts.
                self._read_handle.invalidate()
            handle = self._read_handle if operation_id is None else None
            if handle is None:
                connection = self._connect(_owner=pending, _read_handle=operation_id is None)
                if operation_id is None:
                    handle = ReadHandle(connection)
                    pending._read_handle = handle
                    self._read_handle = handle
            else:
                pending._connection = handle.connection
                pending._read_handle = handle
                connection = handle.connection
                if connection.in_transaction:
                    raise BackendError('busy')
            catalog_data = self._catalog_runtime_data if _catalog_data else None
            if (catalog_data is not None or _register_descriptor is not None) and operation_id is not None:
                from .sqlite_catalog_runtime_data import authorize_write
                connection.set_authorizer(authorize_write)
            try:
                connection.execute('BEGIN IMMEDIATE' if operation_id is not None else 'BEGIN')
                proofs = None
                descriptor = None
                admitted_catalogs = None
                if handle is not None and catalog_data is None and _register_descriptor is None and self._read_admission_cache_allowed():
                    # BEGIN alone does not pin a snapshot. Reading sqlite_schema
                    # takes a real shared read lock before sampling data_version.
                    connection.execute('SELECT rootpage FROM sqlite_schema LIMIT 1').fetchone()
                    if connection.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                        raise BackendError('unsupported')
                    proofs = handle.pin()
                    if handle.admission is not None:
                        from yadinassi.configuration.configuration_inventory_enums import _same
                        if not _same(handle.admission, self._read_admission_descriptor()):
                            raise BackendError('schema_changed')
                        descriptor = handle.admission
                register_identity = None
                if _register_descriptor is not None:
                    if handle is not None: handle.invalidate()
                    register_identity = self._register_runtime_data.admit(
                        connection,_register_descriptor,readonly=operation_id is None)
                elif catalog_data is not None:
                    if handle is not None and connection.execute('PRAGMA journal_mode').fetchone() != ('delete',):
                        raise BackendError('unsupported')
                elif descriptor is None:
                    admitted = self._validate_transaction_admission(connection)
                    if operation_id is not None and admitted is not None:
                        # The manifest and source proved these schemas on
                        # this locked connection. Keep them private to the
                        # writer and its registered leases.
                        from copy import deepcopy
                        admitted_catalogs = deepcopy({s.identity.int:s for s in admitted})
                    if handle is not None and self._read_admission_cache_allowed():
                        current = self._read_admission_descriptor()
                        descriptor = self._read_admission_baseline
                        if descriptor is None:
                            from copy import deepcopy
                            descriptor = deepcopy(current)
                        else:
                            from yadinassi.configuration.configuration_inventory_enums import _same
                            if not _same(descriptor, current):
                                raise BackendError('schema_changed')
                # Ordinary data uses its open descriptor. The raw format-16
                # lane independently proved this UUID and generation 1.
                identity = (catalog_data.identity if catalog_data is not None else
                            (UUID(int=self.database_id.int), 1) if self.format_version == 16 else register_identity)
                view = _View(self, connection, operation_id, admitted_identity=identity,
                             catalog_data=catalog_data, admitted_catalogs=admitted_catalogs)
                if handle is not None:
                    view._read_handle = handle
                if handle is not None and catalog_data is None and _register_descriptor is None:
                    view._validated_sources = handle.pin() if proofs is None else proofs
                    handle._pending_admission = descriptor
                    # Detached values, not authority: a new or changed SQL
                    # epoch must still pass full admission before attaching them.
                    if descriptor is not None:
                        self._read_admission_baseline = descriptor
            except sqlite3.OperationalError:
                raise BackendError('busy') from None
            self._active = view
            return view
        except BaseException as error:
            if self._read_handle is not None: self._read_handle.invalidate()
            try:
                if self._active is not None:
                    _retire_read_handle(self._active)
                    self._active.close()
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
            if self.storage_version not in (3, 4, 6, 7, 8, 9, 10):
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
            if _source_profile_for_issues(self.activation_issues) == DOCUMENT_FORMS_PROFILE:
                imported = self._document_form_source_snapshot(connection)
                return {f.path: f.content for f in imported.files}
            if _source_profile_for_issues(self.activation_issues) in (BUSINESS_PROFILE, REFERENCE_PROFILE):
                imported, _, _, _ = self._business_source_snapshot(connection)
                return {f.path: f.content for f in imported.files}
            if self.storage_version in (5, 6):
                imported, _, _, _ = (self._demo_source_snapshot(connection) if self.storage_version == 6 else self._inert_source_snapshot(connection))
                return {f.path: f.content for f in imported.files}
            count,total = connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
            if not 1 <= count <= _MAX_FILES or total > _MAX_CONFIG_BYTES: raise BackendError('integrity')
            result = {}
            for path, content, digest in connection.execute('SELECT path,content,sha256 FROM configuration_file ORDER BY path'):
                if type(content) is not bytes or type(path) is not str or len(path) > 256 or len(content) > 1024*1024 or hashlib.sha256(content).hexdigest() != digest: raise BackendError('integrity')
                result[path] = content
            return result
        finally: connection.close()

    @lifecycle
    def _close_idle_read_handle(self):
        if self._active is not None: raise BackendError('busy')
        if self._read_handle is not None:
            pending = _PendingConnection(self)
            self._active = pending
            pending._connection = self._read_handle.connection
            pending._read_handle = self._read_handle
            pending.close()

    @lifecycle
    def close(self):
        try:
            if self._active is not None:
                _close_owned_connection(self._active)
            self._close_idle_read_handle()
            from .sqlite_single_statement import close_writer
            close_writer(self)
            self._closed = True
        finally:
            self._prepared_source.clear()
            self._enum_domain = None
            self._read_admission_baseline = None


class _View:
    def __init__(self, backend, connection, operation_id, *, query_language=False,
                 admitted_identity=None, catalog_data=None, admitted_catalogs=None):
        self._backend, self._connection, self._operation_id = backend, connection, operation_id
        self._query_language = query_language
        self._catalog_data = catalog_data
        self._admitted_catalogs = admitted_catalogs
        self._committed = False
        self._closed = False; self._poisoned = False; self._changes = []
        self._scan_cursor = None
        self._validated_sources = {}
        self._read_handle = None
        self._document_scan_stream = None
        self._document_scan_lookahead = None
        self._outcomes = []
        self._section_write_bytes = 0
        self._section_write_rows = 0
        if query_language:
            self.database_id = backend.database_id
            self.configuration_generation = backend.configuration_generation
            return
        if admitted_identity is None:
            row = connection.execute('SELECT database_uuid,generation FROM database_info WHERE singleton=1').fetchone()
            admitted_identity = UUID(row[0]), row[1]
        self.database_id, self.configuration_generation = admitted_identity
        if self.database_id != backend.database_id or self.configuration_generation != backend.configuration_generation:
            raise BackendError('schema_changed')

    @property
    def _catalog_layout(self):
        data = self._catalog_data
        return self._backend._layout if data is None else data.layout

    @property
    def _catalog_sections(self):
        data = self._catalog_data
        return self._backend._section_layout if data is None else data.sections

    @property
    def _catalog_domain(self):
        data = self._catalog_data
        return self._backend._enum_domain if data is None else data.domain

    def _require(self, write=False, mutate=False):
        if self._closed or self._poisoned or self._committed: raise BackendError('closed')
        if write and self._operation_id is None: raise BackendError('unsupported')
        if mutate and len(self._changes) >= _MAX_ROWS: raise BackendError('unsupported')

    @_boundary
    def catalogs(self):
        self._require()
        if self._query_language:
            return self._backend._schemas
        rows = self._connection.execute('SELECT definition FROM catalog_schema ORDER BY name,identity').fetchall()
        if len(rows) > 512: raise BackendError('integrity')
        schemas = tuple(_schema(row[0], allow_numbering=self._backend.storage_version in (4, 6, 7, 8, 9, 10), allow_hierarchy=self._backend.storage_version == 10, enum_domain=self._backend._enum_domain) for row in rows)
        if self._backend.storage_version not in (3, 4, 6, 7, 8, 9, 10) and any(s.tabular_sections for s in schemas):
            raise BackendError('unsupported')
        return schemas

    @_boundary
    def metadata_configuration(self):
        """Current source tree order and name in this same admitted read view.

        Field descriptors are built from logical schemas, never source receipts.
        No configuration code is loaded or executed by this read-only port.
        """
        self._require()
        from yadinassi.configuration.configuration_xml import _object, _props, _text, MD, _XML_WHITESPACE
        row = self._connection.execute("SELECT content,sha256 FROM configuration_file WHERE path='Configuration.xml'").fetchone()
        if (row is None or type(row[0]) is not bytes or len(row[0]) > 1024*1024
                or hashlib.sha256(row[0]).hexdigest() != row[1]): raise BackendError('integrity')
        config, _ = _object(row[0], 'Configuration')
        name = _text(_props(config),'Name')
        expected = self._connection.execute('SELECT name FROM database_info WHERE singleton=1').fetchone()
        if expected is None or expected[0] != name: raise BackendError('schema_changed')
        children = config.find('{'+MD+'}ChildObjects')
        if children is None: raise BackendError('integrity')
        orders = {}
        for family in ('Catalog','Document','InformationRegister'):
            names = tuple((node.text or '').strip(_XML_WHITESPACE) for node in children if node.tag == '{'+MD+'}'+family)
            if len(names) > 512 or len({n.casefold() for n in names}) != len(names): raise BackendError('integrity')
            # Demo profiles admit only a documented subset of their source tree.
            if family == 'Catalog' and self._backend.storage_version == 6:
                admitted = {s.name.casefold() for s in self._backend._schemas}
                names = tuple(n for n in names if n.casefold() in admitted)
            orders[family] = names
        return name, tuple(orders.items())

    @_boundary
    def product_list_sources(self, catalog_id):
        """Exact list/object bytes admitted in this same read-only snapshot."""
        self._require()
        backend = self._backend
        if backend.format_version == 16:
            from yadinassi.configuration.configuration_main_demo import MainDemoConfiguration
            if type(backend.accumulation_configuration) is MainDemoConfiguration:
                if self._operation_id is not None: raise BackendError('unsupported')
                config = backend._main_demo_source_snapshot(self._connection)
                product = next(c for c in config.catalogs if c.name == 'Номенклатура')
                if product.identity != catalog_id: raise BackendError('unsupported')
                files = dict(config.files)
                base = 'Catalogs/Номенклатура/'
                return (files[base+'Forms/ФормаСписка/Ext/Form/Module.bsl'],
                        files[base+'Ext/ObjectModule.bsl'])
        if (self._operation_id is not None or backend.storage_version != 6
                or backend._demo_profile() != DEMO_PRODUCTS_PROFILE):
            raise BackendError('unsupported')
        imported, catalogs, _, _ = backend._demo_source_snapshot(self._connection)
        product = next(c for c in catalogs if c.name == 'Номенклатура')
        if product.identity != catalog_id:
            raise BackendError('unsupported')
        files = {f.path: f.content for f in imported.files}
        base = 'Catalogs/Номенклатура/'
        return (files[base + 'Forms/ФормаСписка/Ext/Form/Module.bsl'],
                files[base + 'Ext/ObjectModule.bsl'])

    @_boundary
    def catalog_schema(self, catalog_id):
        self._require(); _uuid(catalog_id)
        if self._catalog_data is not None:
            return self._catalog_data.catalog(catalog_id)
        if self._admitted_catalogs is not None:
            schema = self._admitted_catalogs.get(catalog_id.int)
            if schema is None: raise BackendError('not_found')
            return schema
        if self._query_language:
            for schema in self._backend._schemas:
                if schema.identity == catalog_id:
                    return schema
            raise BackendError('not_found')
        handle = getattr(self, '_read_handle', None)
        if (self._operation_id is None and handle is not None
                and handle.connection is self._connection
                and handle._pending_admission is not None):
            from yadinassi.configuration.configuration_inventory_enums import _same
            schemas = self._backend._schemas
            if not _same(handle._pending_admission[8], schemas):
                raise BackendError('schema_changed')
            # The pinned snapshot's full admission already checked these exact
            # persisted schemas. No SELECT/JSON decode for each operator.
            for schema in schemas:
                if schema.identity == catalog_id:
                    return schema
            raise BackendError('not_found')
        row = self._connection.execute('SELECT definition FROM catalog_schema WHERE identity=?', (str(catalog_id),)).fetchone()
        if row is None: raise BackendError('not_found')
        schema = _schema(row[0], allow_numbering=self._backend.storage_version in (4, 6, 7, 8, 9, 10), allow_hierarchy=self._backend.storage_version == 10, enum_domain=self._backend._enum_domain)
        if self._backend.storage_version not in (3, 4, 6, 7, 8, 9, 10) and schema.tabular_sections: raise BackendError('unsupported')
        return schema

    def _scalar(self, catalog_id, row, *, schema):
        # Callers have already validated this schema in the same transaction.
        # Reuse it for every row without a per-card SELECT and JSON parse.
        if self._backend.storage_version == 1:
            if type(row[5]) is not str or len(row[5]) > _MAX_ROW_BYTES: raise BackendError('integrity')
            encoded = json.loads(row[5])
        else:
            encoded = decode_typed_columns(row[5:], schema, enum_domain=self._catalog_domain)
        if type(encoded) is not list: raise BackendError('integrity')
        if len(encoded) != len(schema.fields): raise BackendError('integrity')
        if type(row[1]) is not int or not 1 <= row[1] < 2**63 or type(row[2]) is not str or len(row[2]) > schema.code_length or type(row[3]) is not str or len(row[3]) > schema.description_length or type(row[4]) is not int or row[4] not in (0,1): raise BackendError('integrity')
        validate_string(row[2], schema.code_length)
        validate_string(row[3], schema.description_length)
        raw_id = row[0]
        if type(raw_id) is not str or len(raw_id) > 36:
            raise BackendError('integrity')
        key = CatalogKey(self.database_id, catalog_id, UUID(raw_id))
        _uuid(key.record_id)
        revision = Revision(self.database_id,self.configuration_generation,catalog_id,key.record_id,str(row[1]))
        parent, is_folder = hierarchy_storage.values(self,schema,key.record_id)
        return CatalogScalarRow(key,revision,row[2],row[3],bool(row[4]),
                                tuple(_decode(v,f,self.database_id, enum_domain=self._catalog_domain) for v,f in zip(encoded,schema.fields)), parent, is_folder)

    def _card(self, catalog_id, row, section_budget=None, *, schema, sections=_UNLOADED):
        scalar = self._scalar(catalog_id, row, schema=schema)
        if sections is _UNLOADED:
            sections = self._read_sections(schema, scalar.key.record_id, section_budget)
        return CatalogCard(scalar.key, scalar.revision, scalar.code, scalar.description,
                           scalar.deletion_mark, scalar.values, sections, scalar.parent, scalar.is_folder)

    def _section_source(self, schema, section):
        layout = self._catalog_sections
        table = quote_identifier(layout.table_name(schema.identity, section.identity))
        fields = [quote_identifier(layout.field_name(schema.identity, section.identity, f.identity)) for f in section.fields]
        return table, fields

    def _read_sections(self, schema, record_id, budget=None):
        if not schema.tabular_sections: return ()
        if self._backend.storage_version not in (3, 4, 6, 7, 8, 9, 10): raise BackendError('unsupported')
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
                expected = (number_storage(field).lower() if field.kind == 'number'
                            else 'integer' if field.kind == 'boolean' else 'text')
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
                encoded = decode_typed_columns(row[2:], section, enum_domain=self._catalog_domain)
                values.append(TabularRow(identity, tuple(_decode(v, f, self.database_id, enum_domain=self._catalog_domain) for v, f in zip(encoded, section.fields))))
            result.append(TabularSectionRows(section.identity, tuple(values)))
        return tuple(result)

    def _source(self, schema):
        if self._backend.storage_version == 1:
            return ('catalog_record', 'record_id,revision,code,description,deletion_mark,values_json', 'catalog_id=?', (str(schema.identity),))
        fields = ','.join(quote_identifier(self._catalog_layout.field_name(schema.identity, f.identity)) for f in schema.fields)
        return (quote_identifier(self._catalog_layout.table_name(schema.identity)), 'record_id,revision,code,description,deletion_mark' + (',' + fields if fields else ''), '1', ())

    @_boundary
    def _find_catalog_ref_exact(self, catalog_id, field, value):
        """Exact manager reference lookup; no whole-source scan validation."""
        from .sqlite_single_statement import fetch_all

        self._require()
        if type(self) is _View:
            if (self._backend._active is not self or self._operation_id is not None
                    or self._connection is None):
                raise BackendError('closed')
            if not self._query_language and not self._connection.in_transaction:
                raise BackendError('closed')
        # The manager authenticates any registered lease before entering,
        # and it still has its own _require() lifetime gate above.
        if type(field) is not str or field not in ('code','description'):
            raise BackendError('invalid_input')
        self._scan_operand('string',None,value)
        schema = self.catalog_schema(catalog_id)
        if schema.hierarchy != 'none':
            # Check parent membership/cycles, even on a miss. _scalar
            # reuses the one graph held by this admitted view for any hit.
            hierarchy_storage.load(self,schema)
        table, columns, where, args = self._source(schema)
        predicate = quote_identifier(field) + ' COLLATE BINARY = ?'
        if where != '1': predicate = where + ' AND ' + predicate
        rows = fetch_all(self._connection,'SELECT %s FROM %s WHERE %s LIMIT 2'
                         % (columns,table,predicate),args+(value,))
        return tuple(self._scalar(catalog_id,row,schema=schema).key for row in rows)

    @_boundary
    def _catalog_selection_page(self, catalog_id, after, size):
        """One detached BSL manager page, without fetching tabular parts."""
        from yadinassi.db.manager_selection import PAGE_SIZE, MAX_CATALOG_PAGE_SIZE, require_continuation

        self._require()
        if self._operation_id is not None: raise BackendError('unsupported')
        if type(size) is not int or not PAGE_SIZE <= size <= MAX_CATALOG_PAGE_SIZE:
            raise BackendError('invalid_input')
        schema = self.catalog_schema(catalog_id)
        if size > PAGE_SIZE:
            if self._backend.storage_version == 1:
                # The legacy JSON cell may itself use the full row budget.
                size = PAGE_SIZE
            else:
                # Bound growth by the opened declaration, not a data scan.
                # Account conservatively for UTF-8 and narrow typed values.
                text = schema.code_length+schema.description_length+sum(
                    field.qualifiers[0] for field in schema.fields if field.kind=='string')
                row_bytes = 128+128*len(schema.fields)+4*text
                size = min(size,max(PAGE_SIZE,_MAX_CONFIG_BYTES//row_bytes))
        table, columns, where, args = self._source(schema)
        if after is not None:
            require_continuation(after,2)
            # The admitted code column is already BINARY. Adding COLLATE
            # inside the tuple prevents SQLite from seeking into its index.
            where += ' AND (code,record_id)>(?,?)'
            args += after
        cursor = self._connection.execute(
            'SELECT %s FROM %s WHERE %s ORDER BY code COLLATE BINARY,record_id LIMIT ?'
            % (columns,table,where), args+(size,))
        records = []
        try:
            # Do not hold raw copies of the whole larger window alongside
            # the typed rows. Each row still goes through the same decoder.
            for row in cursor:
                records.append(self._scalar(catalog_id,row,schema=schema))
        finally:
            cursor.close()
        return tuple(records), (row[2],row[0]) if len(records)==size else None

    @_boundary
    def select_catalog(self, catalog_id, request=CatalogSelection()):
        self._require(); schema = self.catalog_schema(catalog_id)
        if type(request) is not CatalogSelection or type(request.limit) is not int or not 1 <= request.limit <= _MAX_ROWS or request.order != 'code_then_identity':
            raise BackendError('unsupported')
        table, columns, where, args = self._source(schema)
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

    def _scan_field(self, schema, field, owner_catalog_id=None):
        if type(field) is str:
            kinds = ({'ref': 'catalog_ref'} if owner_catalog_id is not None else
                     {'ref': 'catalog_ref', 'code': 'string',
                      'description': 'string', 'deletion_mark': 'boolean'})
            if owner_catalog_id is None and schema.hierarchy != 'none': kinds.update(parent='catalog_ref',is_folder='boolean')
            if field not in kinds: raise BackendError('invalid_input')
            return kinds[field], (owner_catalog_id or schema.identity) if field in ('ref','parent') else None
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

    def _scan_predicate(self, schema, predicate, budget, depth=0, owner_catalog_id=None):
        budget[0] += 1
        if budget[0] > 64 or depth > 8: raise BackendError('unsupported')
        if type(predicate) is CatalogComparison:
            kind, target = self._scan_field(schema, predicate.field, owner_catalog_id)
            if type(predicate.operator) is not str or predicate.operator not in ('eq','ne','lt','le','gt','ge'): raise BackendError('unsupported')
            if kind == 'catalog_ref' and predicate.operator not in ('eq','ne'): raise BackendError('unsupported')
            self._scan_operand(kind, target, predicate.value)
        elif type(predicate) is CatalogPredicate:
            if type(predicate.kind) is not str or predicate.kind not in ('and','or') or type(predicate.terms) is not tuple or not 1 <= len(predicate.terms) <= 64: raise BackendError('invalid_input')
            for term in predicate.terms:
                self._scan_predicate(schema, term, budget, depth+1, owner_catalog_id)
        else: raise BackendError('invalid_input')

    @staticmethod
    def _scan_value(schema, card, field):
        if type(card) is CatalogSectionRecord:
            if type(field) is str: return card.owner
            return card.row.values[next(i for i, item in enumerate(schema.fields) if item.identity == field)]
        if type(field) is str:
            if field == 'parent': return card.parent or CatalogKey(card.key.database_id,card.key.catalog_id,UUID(int=0))
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

    def _cache_validation_allowed(self):
        return self._operation_id is None

    def _validate_scan_scalars(self, catalog_id, schema, *, retain_owners=False):
        self._require()
        cache_key = ('catalog-scalars', catalog_id, schema, retain_owners)
        if self._cache_validation_allowed() and cache_key in self._validated_sources:
            return set(self._validated_sources[cache_key])
        # Validate actual scalar rows once; filtering must not hide malformed
        # owner values. No preliminary COUNT/SUM or typeof scan is needed.
        table, columns, where, args = self._source(schema)
        owners = set(); seen = 0
        for row in self._connection.execute('SELECT %s FROM %s WHERE %s LIMIT ?' %
                (columns, table, where), args + (_MAX_ROWS + 1,)):
            seen += 1
            if seen > _MAX_ROWS: raise BackendError('unsupported')
            scalar = self._scalar(catalog_id, row, schema=schema)
            if retain_owners: owners.add(str(scalar.key.record_id))
        if self._cache_validation_allowed():
            self._validated_sources[cache_key] = frozenset(owners)
        return owners

    def _scan_sql(self, schema, request):
        # Legacy index iteration can determine stable order for UUID aliases;
        # retain that complete historical path instead of mixing SQL sort rules.
        if self._backend.storage_version == 1 or schema.hierarchy != 'none': return None
        # Native comparison for scaled INTEGER/BLOB; versioned collations for
        # UUID and optional Unicode casefold, never SQLite float or ASCII NOCASE.
        from .sqlite_catalog_numbers import comparison

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
            elif kind == 'number': return column
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
            elif type(value) is decimal.Decimal:
                definition = next(item for item in schema.fields if item.identity == predicate.field)
                return comparison(column, definition, predicate.operator, value)
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
        return predicate[0], predicate[1], ','.join(order), tuple(
            (term.rsplit(' ', 1)[0], term.endswith(' DESC')) for term in order)

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
                        expected = (number_storage(field).lower() if field.kind == 'number'
                                    else 'integer' if field.kind == 'boolean' else 'text')
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
                values = tuple(_decode(v, f, self.database_id, enum_domain=self._backend._enum_domain) for v, f in
                               zip(decode_typed_columns(row[3:], section, enum_domain=self._backend._enum_domain), section.fields))
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
        tags = {'string':'s', 'datetime':'d'}
        for field, value in zip(fields,row[1:]):
            if type(field) is str:
                values.append(key if field == 'ref' else bool(value) if field == 'deletion_mark' else value)
                continue
            definition = definitions[field]
            if definition.kind == 'enum_ref':
                encoded = ['enum_ref_v1', str(definition.target_enum_id), value]
            elif definition.kind == 'catalog_ref':
                encoded = ['r',str(definition.target_catalog_id),value if value is not None else str(UUID(int=0))]
            elif definition.kind == 'boolean':
                if type(value) is not int or value not in (0,1): raise BackendError('integrity')
                encoded = ['b',bool(value)]
            elif definition.kind == 'number':
                values.append(decode_number(value, definition))
                continue
            else: encoded = [tags[definition.kind],value]
            values.append(_decode(encoded,definition,self.database_id, enum_domain=self._backend._enum_domain))
        return CatalogValueRow(key,tuple(values))

    def _aggregate_numeric_catalog(self, catalog_id, request):
        from yadinassi.db.catalog.catalog_backend import CatalogAggregateRequest, CatalogNumericAggregateResult
        from .sqlite_catalog_numbers import aggregate_result
        operations=request.operations
        if type(operations) is not tuple or not 1<=len(operations)<=64:raise BackendError('invalid_input')
        schema=self.catalog_schema(catalog_id);expressions=[];fields=[]
        if (self._operation_id is not None or not self._cache_validation_allowed()
                or self._backend.storage_version<2 or schema.hierarchy!='none'):return None
        for item in operations:
            if type(item) is not tuple or len(item)!=2:raise BackendError('invalid_input')
            operation,identity=item
            if type(operation) is not str:raise BackendError('invalid_input')
            if operation=='count' and identity is None:
                expressions.append('COUNT(*)');fields.append(None);continue
            if operation not in ('sum','avg') or type(identity) is not UUID:raise BackendError('invalid_input')
            field=next((f for f in schema.fields if f.identity==identity),None)
            if field is None or field.kind!='number':raise BackendError('invalid_input')
            column=quote_identifier(self._backend._layout.field_name(schema.identity,identity))
            expressions.append('yadinassi_sum_coefficients_v1('+column+')');fields.append(field)
        # Reuse the existing readonly view's scalar and normalized UUID
        # uniqueness proof. Do not share validation across query-language views.
        proof=self.aggregate_catalog(catalog_id,CatalogAggregateRequest(), _validate=True)
        if proof is None:return None
        table,_,where,args=self._source(schema)
        clause = '' if where == '1' and not args else ' WHERE ' + where
        row=self._connection.execute('SELECT COUNT(*),'+','.join(expressions)+' FROM '+table+clause,args).fetchone()
        if type(row) is not tuple or len(row)!=len(expressions)+1 or type(row[0]) is not int or row[0]!=proof.count:
            raise BackendError('integrity')
        values = tuple(raw if field is None else aggregate_result(raw, proof.count, operation, field)
                       for (operation, _), field, raw in zip(operations, fields, row[1:]))
        return CatalogNumericAggregateResult(proof.count,values)

    @_boundary
    def aggregate_catalog(self, catalog_id, request, *, _validate=False):
        """SQL COUNT with complete-source admission and distinct logical IDs.

        The extra proof is snapshot/connection-local, never a metadata receipt.
        Unsupported storage/transaction shapes decline without changing scans.
        """
        from yadinassi.db.catalog.catalog_backend import CatalogAggregateRequest, CatalogAggregateResult, CatalogNumericAggregateRequest
        self._require()
        if type(request) is CatalogNumericAggregateRequest:
            return self._aggregate_numeric_catalog(catalog_id,request)
        if type(request) is not CatalogAggregateRequest or request.operation != 'count_all_v1':
            raise BackendError('invalid_input')
        schema = self.catalog_schema(catalog_id)
        if (self._operation_id is not None or not self._cache_validation_allowed()
                or self._backend.storage_version < 2 or schema.hierarchy != 'none'):
            return None
        table, _, where, args = self._source(schema)
        if self._query_language and not _validate:
            clause = '' if where == '1' and not args else ' WHERE ' + where
            row = self._connection.execute('SELECT COUNT(*) FROM '+table+clause,args).fetchone()
            return CatalogAggregateResult(row[0])
        self._validate_scan_scalars(catalog_id, schema)
        # An unconditional WHERE disables SQLite's dedicated Count opcode.
        # Keep actual source predicates (notably the shared-table v1 filter).
        clause = '' if where == '1' and not args else ' WHERE ' + where
        proof = ('catalog-count-unique-v1', catalog_id, schema)
        previous = self._validated_sources.get(proof) if self._cache_validation_allowed() else None
        if previous is None:
            # TEXT primary keys do not prove UUID uniqueness: accepted aliases
            # can normalize to one logical identity. Match relational seen-set.
            row = self._connection.execute(
                'SELECT COUNT(*), COUNT(DISTINCT record_id COLLATE yadinassi_uuid_v1) '
                'FROM %s%s' % (table, clause), args).fetchone()
            if (type(row) is not tuple or len(row) != 2
                    or any(type(value) is not int for value in row)
                    or not 0 <= row[0] <= _MAX_ROWS or row[0] != row[1]):
                raise BackendError('integrity')
            count = row[0]
            if self._cache_validation_allowed():self._validated_sources[proof] = (count,)
        else:
            row = self._connection.execute('SELECT COUNT(*) FROM %s%s' % (table,clause),args).fetchone()
            if (type(previous) is not tuple or len(previous) != 1 or type(previous[0]) is not int
                    or type(row) is not tuple or len(row) != 1 or type(row[0]) is not int
                    or row != previous):
                raise BackendError('integrity')
            count = row[0]
        return CatalogAggregateResult(count)

    @_boundary
    def scan_catalog(self, catalog_id, request):
        return self._scan_catalog(catalog_id, request, None)

    @_boundary
    def scan_catalog_values(self, catalog_id, request, fields):
        if type(fields) is not tuple or not 1 <= len(fields) <= 128:
            raise BackendError('invalid_input')
        return self._scan_catalog(catalog_id, request, fields)

    def _validate_catalog_scan(self, schema, request, fields, max_rows):
        if type(request) is not CatalogScanRequest or type(request.page_size) is not int or not 1 <= request.page_size <= max_rows or type(request.order) is not tuple or len(request.order) > 16: raise BackendError('invalid_input')
        if type(request.string_comparison) is not str or request.string_comparison not in ('codepoint','casefold_v1'): raise BackendError('unsupported')
        if request.predicate is not None: self._scan_predicate(schema,request.predicate,[0])
        if fields is not None:
            for field in fields: self._scan_field(schema, field)
        seen = set()
        for item in request.order:
            if type(item) is not CatalogOrder or type(item.descending) is not bool: raise BackendError('invalid_input')
            if self._scan_field(schema,item.field)[0] == 'enum_ref': raise BackendError('unsupported')
            if item.field in seen: raise BackendError('invalid_input')
            seen.add(item.field)
    @_boundary
    def ordered_catalog_values(self, catalog_id, request, fields):
        """One bounded ordered or point page on a query-only read view."""
        self._require()
        if not self._query_language or self._operation_id is not None: return None
        if self._backend._active is not self: raise BackendError('closed')
        schema = self.catalog_schema(catalog_id)
        if self._backend.storage_version == 1 or schema.hierarchy != 'none': return None
        if (type(request) is not CatalogScanRequest or request.continuation is not None
                or type(fields) is not tuple or not 1 <= len(fields) <= 128):
            raise BackendError('invalid_input')
        try:
            self._validate_catalog_scan(schema, request, fields, _MAX_ROWS)
        except BackendError as error:
            if error.code != 'unsupported': raise
            return None
        predicate = request.predicate
        if not request.order and (type(predicate) is not CatalogComparison or predicate.operator != 'eq'
                                  or predicate.field not in ('code', 'ref')):
            raise BackendError('invalid_input')
        plan = self._scan_sql(schema,request)
        if plan is None: return None
        if self._scan_cursor is not None:
            self._scan_cursor = None
        _close_document_scan(self)
        table, _, source, args = self._source(schema)
        where = ' AND '.join(term for term in (source, plan[0]) if term != '1')
        if where: where = ' WHERE ' + where
        columns = self._projection_columns(schema,fields)
        lengths = {'code':schema.code_length, 'description':schema.description_length}
        texts = tuple((i,lengths[field]) for i,field in enumerate(fields,1) if field in lengths)
        marked = fields.index('deletion_mark')+1 if 'deletion_mark' in fields else None
        cursor = self._connection.execute(
            'SELECT %s FROM %s%s ORDER BY %s LIMIT ?' % (columns,table,where,plan[2]),
            args+plan[1]+(request.page_size,))
        rows = []
        try:
            for row in cursor:
                if type(row[0]) is not str or len(row[0]) > 36: raise BackendError('integrity')
                for i, length in texts:
                    validate_string(row[i], length)
                if marked is not None and (type(row[marked]) is not int or row[marked] not in (0,1)):
                    raise BackendError('integrity')
                rows.append(self._projection_row(catalog_id,schema,fields,row))
        finally: cursor.close()
        self._require()
        if self._backend._active is not self: raise BackendError('closed')
        return CatalogValuePage(tuple(rows),None)

    def _scan_catalog(self, catalog_id, request, fields):
        self._require()
        _close_document_scan(self)
        if self._operation_id is not None: raise BackendError('unsupported')
        schema = self.catalog_schema(catalog_id)
        self._validate_catalog_scan(schema, request, fields, 1000)
        binding = ('catalog',catalog_id,request.predicate,request.order,request.page_size,request.string_comparison,fields)
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
            # The continuation stores the last physical sort key, not an offset.
            # Include rowid after logical UUID to preserve accepted UUID aliases.
            key_columns = tuple(column for column, descending in plan[3])
            seek, seek_args = '1', ()
            if type(offset) is tuple:
                clauses, arguments = [], []
                for i, (column, descending) in enumerate(plan[3]):
                    clauses.append('(' + ' AND '.join(
                        [key_columns[j] + ' = ?' for j in range(i)] +
                        [column + (' < ?' if descending else ' > ?')]) + ')')
                    arguments.extend(offset[:i + 1])
                seek, seek_args = '(' + ' OR '.join(clauses) + ')', tuple(arguments)
            rows = self._connection.execute(
                'SELECT %s,%s FROM %s WHERE (%s) AND (%s) AND (%s) ORDER BY %s LIMIT ?' %
                (projection_columns or columns, ','.join(key_columns), table, source_where, plan[0], seek, plan[2]),
                source_args + plan[1] + seek_args + (request.page_size + 1,)).fetchall()
            next_key = tuple(rows[min(len(rows), request.page_size) - 1][-len(key_columns):]) if rows else None
            rows = [row[:-len(key_columns)] for row in rows]
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
        self._scan_cursor = None if token is None else (token,binding,(offset+len(rows) if plan is None else next_key),fallback)
        return CatalogPage(items,token) if fields is None else CatalogValuePage(items,token)

    def _preflight_section_scan(self, schema, section):
        """Bound and validate the complete chosen source before fetching rows.

        The source is one section, never a flatten of owner cards. No predicate
        or TOP can conceal corrupt rows or reduce this pre-materialization
        budget. Other section payloads and owner attributes are not loaded.
        """
        table, fields = self._section_source(schema, section)
        invalid = ["typeof(owner_id)!='text'", "length(CAST(owner_id AS BLOB))!=36",
                   "typeof(row_id)!='text'", "length(CAST(row_id AS BLOB))!=36",
                   "typeof(row_number)!='integer'", 'row_number<1',
                   'row_number>%d' % _MAX_SECTION_ROWS]
        lengths = ['36', '36', '16']
        for field, column in zip(section.fields, fields):
            expected = (number_storage(field).lower() if field.kind == 'number'
                            else 'integer' if field.kind == 'boolean' else 'text')
            nullable = field.kind == 'catalog_ref'
            invalid.append(f'({column} IS NOT NULL AND typeof({column})!=\'{expected}\')'
                           if nullable else f'typeof({column})!=\'{expected}\'')
            limit = field.qualifiers[0] * 4 if field.kind == 'string' else (36 if nullable else 64)
            invalid.append('length(CAST(%s AS BLOB))>%d' % (column, limit))
            lengths.append('COALESCE(length(CAST(%s AS BLOB)),0)' % column)
        if self._connection.execute('SELECT 1 FROM %s WHERE %s LIMIT 1' %
                                    (table, ' OR '.join(invalid))).fetchone():
            raise BackendError('integrity')
        size = '+'.join(lengths)
        count, total = self._connection.execute(
            'SELECT COUNT(*),COALESCE(SUM(%s),0) FROM %s' % (size, table)).fetchone()
        if (type(count) is not int or type(total) is not int
                or count > _MAX_ROWS or total > _MAX_CONFIG_BYTES):
            raise BackendError('unsupported')
        if self._connection.execute(
                'SELECT 1 FROM %s GROUP BY owner_id HAVING COUNT(*)>? OR SUM(%s)>? LIMIT 1' %
                (table, size), (_MAX_SECTION_ROWS, _MAX_ROW_BYTES)).fetchone():
            raise BackendError('unsupported')
        if self._connection.execute(
                'SELECT 1 FROM %s GROUP BY owner_id HAVING MIN(row_number)!=1 '
                'OR MAX(row_number)!=COUNT(*) OR COUNT(DISTINCT row_number)!=COUNT(*) LIMIT 1' % table).fetchone():
            raise BackendError('integrity')
        owner_table = quote_identifier(self._backend._layout.table_name(schema.identity))
        # A direct scan must reject orphans, not silently hide them with a join.
        if self._connection.execute(
                'SELECT 1 FROM %s AS s WHERE NOT EXISTS '
                '(SELECT 1 FROM %s AS o WHERE o.record_id=s.owner_id) LIMIT 1' %
                (table, owner_table)).fetchone():
            raise BackendError('integrity')
        for field, column in zip(section.fields, fields):
            if field.kind != 'catalog_ref': continue
            target = quote_identifier(self._backend._layout.table_name(field.target_catalog_id))
            if self._connection.execute(
                    'SELECT 1 FROM %s AS s WHERE s.%s IS NOT NULL AND NOT EXISTS '
                    '(SELECT 1 FROM %s AS t WHERE t.record_id=s.%s) LIMIT 1' %
                    (table, column, target, column)).fetchone():
                raise BackendError('integrity')
        return table, fields, count

    def _section_scan_records(self, schema, section):
        table, fields, count = self._preflight_section_scan(schema, section)
        columns = 'owner_id,row_id,row_number' + (',' + ','.join(fields) if fields else '')
        rows = self._connection.execute(
            'SELECT %s FROM %s ORDER BY owner_id,row_number LIMIT ?' % (columns, table),
            (_MAX_ROWS + 1,)).fetchall()
        if len(rows) != count: raise BackendError('integrity')
        records = []
        seen = set()
        positions = {}
        # Decode every row and every field before filtering or returning a page.
        for row in rows:
            owner_id, row_id = UUID(row[0]), UUID(row[1])
            if (not owner_id.int or not row_id.int or str(owner_id) != row[0]
                    or str(row_id) != row[1] or (owner_id, row_id) in seen):
                raise BackendError('integrity')
            seen.add((owner_id, row_id))
            position = positions.get(owner_id, 0) + 1
            if type(row[2]) is not int or row[2] != position:
                raise BackendError('integrity')
            positions[owner_id] = position
            encoded = decode_typed_columns(row[3:], section, enum_domain=self._backend._enum_domain)
            values = tuple(_decode(value, field, self.database_id, enum_domain=self._backend._enum_domain)
                           for value, field in zip(encoded, section.fields))
            owner = CatalogKey(self.database_id, schema.identity, owner_id)
            records.append(CatalogSectionRecord(owner, section.identity, TabularRow(row_id, values)))
        return records

    @_boundary
    def ordered_catalog_part(self, catalog_id, section_id, request, fields):
        from .sqlite_ordered_parts import ordered_part_rows
        self._require()
        if not self._query_language or self._operation_id is not None: return None
        catalog = self.catalog_schema(catalog_id)
        _uuid(section_id)
        section = next((part for part in catalog.tabular_sections if part.identity==section_id),None)
        if section is None: raise BackendError('not_found')
        if type(fields) is not tuple or not 1<=len(fields)<=128: raise BackendError('invalid_input')
        for field in fields: self._scan_field(section,field,catalog_id)
        table, physical = self._section_source(catalog,section)
        parent = quote_identifier(self._backend._layout.table_name(catalog_id))
        rows = ordered_part_rows(self,request,section,table,physical,parent,catalog_id)
        if rows is None: return None
        return CatalogSectionPage(tuple(CatalogSectionRecord(CatalogKey(self.database_id,catalog_id,owner),
            section_id,TabularRow(row,values)) for owner,row,_,values,_ in rows),None)

    @_boundary
    def scan_catalog_section(self, catalog_id, section_id, request):
        """Read-only typed section scan in the same pinned read-view contract."""
        self._require()
        _close_document_scan(self)
        if self._operation_id is not None or self._backend.storage_version not in (3, 4, 6, 7, 8, 9, 10):
            raise BackendError('unsupported')
        schema = self.catalog_schema(catalog_id)
        _uuid(section_id)
        section = next((item for item in schema.tabular_sections if item.identity == section_id), None)
        if section is None: raise BackendError('not_found')
        if (type(request) is not CatalogScanRequest or type(request.page_size) is not int
                or not 1 <= request.page_size <= 1000 or type(request.order) is not tuple
                or len(request.order) > 16):
            raise BackendError('invalid_input')
        if (type(request.string_comparison) is not str
                or request.string_comparison not in ('codepoint', 'casefold_v1')):
            raise BackendError('unsupported')
        if request.predicate is not None:
            self._scan_predicate(section, request.predicate, [0], owner_catalog_id=catalog_id)
        seen = set()
        for item in request.order:
            if type(item) is not CatalogOrder or type(item.descending) is not bool:
                raise BackendError('invalid_input')
            if self._scan_field(section, item.field, catalog_id)[0] == 'enum_ref': raise BackendError('unsupported')
            if item.field in seen: raise BackendError('invalid_input')
            seen.add(item.field)
        binding = ('section', catalog_id, section_id, request.predicate, request.order,
                   request.page_size, request.string_comparison)
        if request.continuation is not None:
            if type(request.continuation) is not str or len(request.continuation) != 32:
                raise BackendError('invalid_input')
            cursor = self._scan_cursor
            if cursor is None or cursor[0] != request.continuation or cursor[1] != binding:
                raise BackendError('invalid_input')
            records, offset = cursor[2], cursor[3]
        else:
            self._scan_cursor = None
            records = self._section_scan_records(schema, section)
            records = [row for row in records if self._scan_matches(
                section, row, request.predicate, request.string_comparison)]
            def compare(left, right):
                for item in request.order:
                    a = self._scan_value(section, left, item.field)
                    b = self._scan_value(section, right, item.field)
                    if type(a) is str and request.string_comparison == 'casefold_v1':
                        a, b = a.casefold(), b.casefold()
                    if type(a) is CatalogKey: a, b = a.record_id.int, b.record_id.int
                    result = (a > b) - (a < b)
                    if result: return -result if item.descending else result
                a = (left.owner.record_id.int, left.row.identity.int)
                b = (right.owner.record_id.int, right.row.identity.int)
                return (a > b) - (a < b)
            records = tuple(sorted(records, key=cmp_to_key(compare)))
            offset = 0
        end = offset + request.page_size
        page = records[offset:end]
        token = uuid4().hex if end < len(records) else None
        self._scan_cursor = None if token is None else (token, binding, records, end)
        return CatalogSectionPage(page, token)

    @_boundary
    def read_catalog(self, key):
        self._require(); self._key(key)
        schema = self.catalog_schema(key.catalog_id)
        table, columns, where, args = self._source(schema)
        row = self._connection.execute('SELECT %s FROM %s WHERE %s AND record_id=?' % (columns,table,where), args+(str(key.record_id),)).fetchone()
        return None if row is None else self._card(key.catalog_id,row,schema=schema)

    @_boundary
    def read_catalog_values(self, key, fields):
        """Point projection after full selected-record integrity admission.

        No writer can borrow this proof. ReadHandle invalidates it on source,
        schema or data changes. Legacy/hierarchy paths keep their full reader.
        """
        self._require(); self._key(key)
        if self._operation_id is not None: raise BackendError('unsupported')
        schema = self.catalog_schema(key.catalog_id)
        if type(fields) is not tuple or not 1 <= len(fields) <= 128:
            raise BackendError('invalid_input')
        for field in fields: self._scan_field(schema,field)
        if self._backend.storage_version == 1 or schema.hierarchy != 'none':
            card = self.read_catalog(key)
            return None if card is None else CatalogValueRow(key,tuple(
                self._scan_value(schema,card,field) for field in fields))
        table, columns, where, args = self._source(schema)
        args += (str(key.record_id),)
        proof = ('catalog-point',key.catalog_id,schema,key.record_id)
        if proof not in self._validated_sources:
            row = self._connection.execute('SELECT %s FROM %s WHERE %s AND record_id=?' %
                (columns,table,where),args).fetchone()
            if row is not None:
                scalar = self._scalar(key.catalog_id,row,schema=schema)
                owner = str(scalar.key.record_id)
                self._section_scan(schema,(owner,),selected=(owner,))
            self._validated_sources[proof] = ()
        row = self._connection.execute('SELECT %s FROM %s WHERE %s AND record_id=?' %
            (self._projection_columns(schema,fields),table,where),args).fetchone()
        return None if row is None else self._projection_row(key.catalog_id,schema,fields,row)

    def _key(self,key):
        if type(key) is not CatalogKey or key.database_id != self.database_id: raise BackendError('invalid_input')
        _uuid(key.catalog_id); _uuid(key.record_id, empty=True)

    def _draft(self,draft):
        if type(draft) is not CatalogDraft or type(draft.auto_number) is not bool or type(draft.code) is not str: raise BackendError('invalid_input')
        self._key(draft.key); _uuid(draft.key.record_id)
        schema = self.catalog_schema(draft.key.catalog_id)
        hierarchy_storage.check_draft(self,schema,draft)
        if draft.auto_number and (schema.numbering != 'decimal_v1' or draft.code != '' or self._backend.storage_version not in (4, 6, 7, 8, 9, 10)):
            raise BackendError('invalid_input')
        if schema.numbering == 'decimal_v1' and not draft.auto_number and draft.code == '':
            raise BackendError('invalid_input')
        if type(draft.deletion_mark) is not bool or type(draft.values) is not tuple or len(draft.values)!=len(schema.fields):
            raise BackendError('invalid_input')
        try:
            draft = replace(draft, code=normalize_string(draft.code,schema.code_length),
                            description=normalize_string(draft.description,schema.description_length),
                            values=tuple(normalize_field(v,f) for v,f in zip(draft.values,schema.fields)))
        except (ValueError, TypeError): raise BackendError('invalid_input') from None
        values = [_encode(v,f,self.database_id, enum_domain=self._catalog_domain) for v,f in zip(draft.values,schema.fields)]
        for value in draft.values:
            if type(value) is CatalogKey and value.record_id.int and not self._reference_exists(value):
                raise BackendError('not_found')
        encoded = _json(values)
        if len(encoded.encode('utf-8')) > _MAX_ROW_BYTES: raise BackendError('invalid_input')
        return draft, encoded, schema

    def _reference_exists(self, key):
        schema = self.catalog_schema(key.catalog_id)
        table, _, where, args = self._source(schema)
        return self._connection.execute('SELECT 1 FROM %s WHERE %s AND record_id=?' % (table, where), args + (str(key.record_id),)).fetchone() is not None

    def _draft_sections(self, draft, schema, *, physical=None):
        sections = draft.tabular_sections
        if sections is None: return None
        sparse = type(sections) is _TabularSectionChanges
        if sparse: sections = sections.sections
        if type(sections) is not tuple or len(sections) > _MAX_SECTIONS: raise BackendError('invalid_input')
        if self._backend.storage_version not in (3, 4, 6, 7, 8, 9, 10) and sections: raise BackendError('unsupported')
        references = []
        try:
            result = self._encode_draft_sections(schema,sections,sparse,physical,references)
        except BackendError:
            # An earlier row's missing reference still takes precedence
            # over a later malformed row or exhausted payload budget.
            self._require_section_references(references)
            raise
        self._require_section_references(references)
        return result

    def _require_section_references(self, references):
        if not references: return
        from .sqlite_catalog_layout import reference_presence

        def source(identity):
            table, _, where, args = self._source(self.catalog_schema(identity))
            return table, where, args

        present = reference_presence(self._connection,references,source)
        if not all(present.values()): raise BackendError('not_found')

    def _encode_draft_sections(self, schema, sections, sparse, physical, references):
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
            encoded_rows = [] if physical is not None else None
            for row in section.rows:
                if type(row) is not TabularRow: raise BackendError('invalid_input')
                identity = _uuid(row.identity)
                if identity in seen or type(row.values) is not tuple or len(row.values) != len(definition.fields):
                    raise BackendError('invalid_input')
                seen.add(identity)
                try:
                    values = [_encode(normalize_field(v, f), f, self.database_id, enum_domain=self._catalog_domain) for v, f in zip(row.values, definition.fields)]
                except (ValueError, TypeError): raise BackendError('invalid_input') from None
                references.extend(value for value in row.values if type(value) is CatalogKey and value.record_id.int)
                encoded_row = [identity, values]
                size += len(_json(encoded_row)) + 1
                columns = encode_typed_columns(values, definition, enum_domain=self._catalog_domain)
                stored_size += 52 + sum(len(value.encode('utf-8')) if type(value) is str else (1 if type(value) is int else 0) for value in columns)
                if size > _MAX_ROW_BYTES or stored_size > _MAX_ROW_BYTES: raise BackendError('invalid_input')
                rows.append(encoded_row)
                if encoded_rows is not None: encoded_rows.append((identity,columns))
            supplied[section.section_id] = rows
            if physical is not None: physical[section.section_id] = encoded_rows
        # Canonical order is UUID-based, independent of mutable metadata names
        # and caller ordering of sections. Row sequence remains significant.
        targets = supplied if sparse else by_id
        result = [[str(identity), supplied.get(identity, [])] for identity in sorted(targets, key=lambda x: x.hex)]
        if len(_json(result)) > _MAX_ROW_BYTES: raise BackendError('invalid_input')
        return result

    def _write_sections(self, draft, schema, sections, physical, *, create):
        if sections is None or not schema.tabular_sections: return
        from .sqlite_section_delta import read_physical_rows, write_section

        owner_columns = ('owner_id',)
        owner = (str(draft.key.record_id),)
        included = {identity for identity,_ in sections}
        for section in schema.tabular_sections:
            if str(section.identity) not in included: continue
            rows = physical.get(section.identity,())
            table, fields = self._section_source(schema, section)
            previous = () if create or not rows else read_physical_rows(
                self._connection,table,owner_columns,owner,fields,section.fields,_MAX_SECTION_ROWS)
            write_section(self._connection,table,owner_columns,owner,fields,rows,
                          create=create,max_rows=_MAX_SECTION_ROWS,previous=previous)

    @contextmanager
    def _atomic_record(self):
        # A caller may catch a failed write and still commit previous writes.
        # SQL and its typed outcome bookkeeping are one atomic operation. Journal
        # updates replace lists rather than mutating these saved references.
        before = (self._changes, self._section_write_bytes, self._section_write_rows, self._outcomes)
        self._connection.execute('SAVEPOINT catalog_record_write')
        try:
            yield
            self._connection.execute('RELEASE catalog_record_write')
        except BaseException:
            # An interrupted/failed restoration can never leave commit enabled.
            self._poisoned = True
            hierarchy_storage.clear(self)
            self._changes, self._section_write_bytes, self._section_write_rows, self._outcomes = before
            try:
                self._connection.execute('ROLLBACK TO catalog_record_write')
                self._connection.execute('RELEASE catalog_record_write')
            except BaseException:
                self.close()
            else:
                self._poisoned = False
            raise

    def _section_write_budget(self, sections):
        if sections is not None:
            size = len(_json(sections))
            rows = sum(len(rows) for _, rows in sections)
            if self._section_write_bytes + size > _MAX_CONFIG_BYTES or self._section_write_rows + rows > _MAX_ROWS:
                raise BackendError('unsupported')

    def _allocate_code(self, schema, table):
        schemas = (self._backend._schemas if self._catalog_data is None
                   else self._catalog_data.schemas.values())
        self._backend._check_sequences(self._connection, schemas)
        candidate = self._connection.execute('SELECT next_value FROM catalog_sequence WHERE catalog_id=?',
            (str(schema.identity),)).fetchone()[0]
        ceiling = 10 ** schema.code_length
        # The admitted source contains at most _MAX_ROWS records. This bounds
        # collision skipping without relying on user-controlled numeric casts.
        for unused in range(_MAX_ROWS + 1):
            if candidate >= ceiling: raise BackendError('code_exhausted')
            code = str(candidate).zfill(schema.code_length)
            candidate += 1
            if self._connection.execute('SELECT 1 FROM %s WHERE code=?' % table, (code,)).fetchone() is None:
                self._connection.execute('UPDATE catalog_sequence SET next_value=? WHERE catalog_id=?',
                    (candidate, str(schema.identity)))
                return code
        raise BackendError('unsupported')

    @_boundary
    def create(self,draft):
        self._require(True, mutate=True); draft, values, schema = self._draft(draft)
        physical = {}
        sections = self._draft_sections(draft, schema, physical=physical); self._section_write_budget(sections)
        table, columns, where, args = self._source(schema)
        clause = '' if where == '1' and not args else ' WHERE ' + where
        if self._connection.execute('SELECT COUNT(*) FROM %s%s' % (table,clause),args).fetchone()[0] >= _MAX_ROWS:
            raise BackendError('unsupported')
        with self._atomic_record():
            hierarchy_storage.prepare(self,schema,draft,creating=True)
            if draft.auto_number:
                draft = replace(draft, code=self._allocate_code(schema, table))
            try:
                if self._backend.storage_version == 1:
                    self._connection.execute('INSERT INTO catalog_record VALUES(?,?,1,?,?,?,?)',(str(draft.key.catalog_id),str(draft.key.record_id),draft.code,draft.description,int(draft.deletion_mark),values))
                else:
                    vals = (str(draft.key.record_id),1,draft.code,draft.description,int(draft.deletion_mark))+encode_typed_columns(json.loads(values),schema, enum_domain=self._catalog_domain)
                    self._connection.execute('INSERT INTO %s (%s) VALUES(%s)' % (table,columns,','.join('?' for _ in vals)),vals)
            except sqlite3.IntegrityError:
                raise BackendError('duplicate_identity' if self._reference_exists(draft.key) else 'duplicate_code') from None
            hierarchy_storage.store(self,schema,draft,creating=True)
            self._write_sections(draft,schema,sections,physical,create=True)
            self._record_change(draft,1,sections)

    @_boundary
    def update(self,draft,expected_revision):
        self._require(True, mutate=True); draft, values, schema = self._draft(draft)
        if draft.auto_number: raise BackendError('invalid_input')
        physical = {}
        sections = self._draft_sections(draft, schema, physical=physical); self._section_write_budget(sections)
        revision = self._expected_revision(draft, expected_revision)
        with self._atomic_record():
            try:
                hierarchy_storage.prepare(self,schema,draft,creating=False)
                sql, parameters = self._catalog_update_statement(draft, values, schema, revision)
                cursor = self._connection.execute(sql, parameters)
            except sqlite3.IntegrityError: raise BackendError('duplicate_code') from None
            if cursor.rowcount != 1: raise BackendError('conflict')
            hierarchy_storage.store(self,schema,draft,creating=False)
            self._write_sections(draft,schema,sections,physical,create=False)
            self._record_change(draft,revision+1,sections)

    def _expected_revision(self, draft, revision):
        if (type(revision) is not Revision
                or (revision.database_id,revision.configuration_generation,revision.catalog_id,revision.record_id) !=
                   (self.database_id,self.configuration_generation,draft.key.catalog_id,draft.key.record_id)):
            raise BackendError('conflict')
        return _revision_number(revision.token)

    def _catalog_update_statement(self, draft, values, schema, revision, *, require_unique=False):
        table, _, where, args = self._source(schema)
        base = (draft.code,draft.description,int(draft.deletion_mark))
        record_id = str(draft.key.record_id)
        if self._backend.storage_version == 1:
            return ('UPDATE catalog_record SET revision=revision+1,code=?,description=?,deletion_mark=?,values_json=? WHERE catalog_id=? AND record_id=? AND revision=?',
                    base+(values,str(draft.key.catalog_id),record_id,revision))
        sets = ['revision=revision+1','code=?','description=?','deletion_mark=?'] + [quote_identifier(self._catalog_layout.field_name(schema.identity, f.identity))+'=?' for f in schema.fields]
        parameters = base+encode_typed_columns(json.loads(values),schema, enum_domain=self._catalog_domain)+args+(record_id,revision)
        sql = 'UPDATE %s SET %s WHERE %s AND record_id=? AND revision=?' % (table,','.join(sets),where)
        if require_unique:
            # Normally the admitted PK makes this an indexed point lookup.
            # Guard cardinality inside the statement: an implicit UPDATE has
            # already committed by the time the caller sees its rowcount.
            sql += ' AND NOT EXISTS (SELECT 1 FROM %s WHERE record_id=? LIMIT 1 OFFSET 1)' % table
            parameters += (record_id,)
        return sql, parameters

    def _record_change(self,draft,revision,sections):
        # Prepare every potentially allocating operation before replacing state.
        # A later RELEASE failure can restore the old references without slicing
        # or copying a possibly half-appended journal under memory pressure.
        changes = [*self._changes, Revision(self.database_id,self.configuration_generation,draft.key.catalog_id,draft.key.record_id,str(revision))]
        outcomes = [*self._outcomes, CatalogWriteOutcome(changes[-1],draft.code)]
        size, rows = self._section_write_bytes, self._section_write_rows
        if sections is not None:
            size += len(_json(sections))
            rows += sum(len(part) for _, part in sections)
        self._changes, self._outcomes = changes, outcomes
        self._section_write_bytes, self._section_write_rows = size, rows

    @_boundary
    def commit_outcomes(self, *, _close=True):
        if self._backend.storage_version not in (4, 6, 7, 8, 9, 10): raise BackendError('unsupported')
        outcomes = tuple(self._outcomes)
        if _close:
            self.commit()
        else:
            self.commit(_close=False)
        return outcomes

    @_boundary
    def commit(self, *, _close=True):
        self._require(True)
        revisions = tuple(self._changes)
        try:
            _confirm_sqlite_commit(self._connection)
        except BaseException as error:
            self._poisoned = True
            if _close:
                try: self.close()
                except BaseException as cleanup_error:
                    if _interruption(cleanup_error) and not _interruption(error): raise
            raise
        self._committed = True
        if _close:
            self.close()
        return revisions

    def rollback(self): self.close()
    @lifecycle
    def close(self):
        handle = self._read_handle
        if (self._query_language and not self._closed and not self._poisoned
                and handle is not None and self._connection is handle.connection
                and not self._connection.in_transaction):
            try:
                _close_document_scan(self)
                self._scan_cursor = None
                self._backend._check_file()
                self._validated_sources.clear()
                self._closed = True
                self._connection = self._read_handle = None
                self._backend._active = None
            except BaseException:
                _close_owned_connection(self)
                raise
            return
        if (self._closed or handle is None or self._poisoned
                or self._connection is not handle.connection):
            _close_owned_connection(self)
            return
        try:
            self._closed = True
            self._scan_cursor = None
            _close_document_scan(self)
            self._backend._check_file()
            if not self._connection.in_transaction:
                _close_owned_connection(self)
                return
            self._connection.execute('ROLLBACK')
            if self._catalog_data is None:
                handle.complete(self._validated_sources)
            self._validated_sources.clear()
            self._connection = None
            self._read_handle = None
            if self._backend._active is self:
                self._backend._active = None
        except BaseException as error:
            # Cleanup failure must physically retire the handle. If close also
            # fails, the existing owner remains busy and can retry cleanup.
            try: _close_owned_connection(self)
            except BaseException as cleanup:
                if _interruption(cleanup) and not _interruption(error): raise
            if isinstance(error, sqlite3.Error):
                raise BackendError('storage_error') from None
            raise

# The document port shares the same closed storage error boundary.
for _document_method in ('_validate_query_source','query_dereference','documents','document_schema','read_document','read_document_values','select_documents','_document_selection_page','scan_documents','scan_document_values','ordered_document_values','ordered_document_part','find_document_number','_find_document_number_point','_write_admitted','registers','register_schema','scan_register','ordered_register_records','periodic_records','create','update','commit'):
    setattr(DocumentView, _document_method, _boundary(getattr(DocumentView, _document_method)))

install_boundaries(_boundary)


def _preflight_create(configuration, *, activate=True, query_indexes=False, _source_profile=None):
    """Pure deterministic creation admission; no file, connection or execution."""
    from yadinassi.configuration.configuration_xml import ConfigurationImport, ConfigurationFile, ConfigurationModule
    if type(configuration) is not ConfigurationImport or type(configuration.catalogs) is not tuple or type(configuration.files) is not tuple or type(configuration.modules) is not tuple or type(configuration.activation_issues) is not tuple:
        raise BackendError('invalid_input')
    if type(activate) is not bool or type(query_indexes) is not bool: raise BackendError('invalid_input')
    if _source_profile is not None and (type(_source_profile) is not str or _source_profile not in (*_DEMO_SOURCE_ISSUES, CATALOG_FORMS_PROFILE, APPLICATION_PROFILE, DOCUMENT_FORMS_PROFILE, BUSINESS_PROFILE, REFERENCE_PROFILE) or not activate): raise BackendError('unsupported')
    if _source_profile is None and _source_profile_for_issues(configuration.activation_issues) is not None: raise BackendError('unsupported')
    if activate and configuration.activation_issues and _source_profile is None: raise BackendError('unsupported')
    if len(configuration.activation_issues) > 2048 or any(type(v) is not str or len(v) > 1024 for v in configuration.activation_issues) or len(_json(configuration.activation_issues)) > 65536: raise BackendError('invalid_input')
    if type(configuration.name) is not str or not configuration.name or len(configuration.name) > 128:
        raise BackendError('invalid_input')
    if any(type(f) is not ConfigurationFile for f in configuration.files) or any(type(m) is not ConfigurationModule for m in configuration.modules):
        raise BackendError('invalid_input')
    if configuration.module_runtime is not None:
        from yadinassi.configuration.configuration_modules import MODULE_RUNTIME
        from yadinassi.configuration.configuration_xml import import_configuration
        from yadinassi.types.errors import BSLError
        if type(configuration.module_runtime) is not str or configuration.module_runtime != MODULE_RUNTIME:
            raise BackendError('unsupported')
        if _source_profile not in (None, APPLICATION_PROFILE, BUSINESS_PROFILE, REFERENCE_PROFILE): raise BackendError('unsupported')
        try:
            if _source_profile == REFERENCE_PROFILE:
                from yadinassi.configuration.configuration_reference_profile import import_reference_configuration
                canonical = import_reference_configuration({f.path:f.content for f in configuration.files})
            elif _source_profile == BUSINESS_PROFILE:
                from yadinassi.configuration.configuration_business_profile import import_business_configuration
                canonical = import_business_configuration({f.path:f.content for f in configuration.files})
            elif _source_profile == APPLICATION_PROFILE:
                from yadinassi.configuration.configuration_application_profile import import_application_configuration
                canonical = import_application_configuration({f.path:f.content for f in configuration.files})
            else:
                canonical = import_configuration({f.path:f.content for f in configuration.files},
                    numbering_policy='decimal_v1', module_runtime=MODULE_RUNTIME)
        except (BSLError, ValueError, TypeError):
            raise BackendError('unsupported') from None
        if canonical != configuration: raise BackendError('unsupported')
    elif configuration.common_modules:
        raise BackendError('unsupported')
    registers = configuration.information_registers
    if type(registers) is not tuple: raise BackendError('invalid_input')
    register_definitions = [register_schema_data(r) for r in registers]
    documents = configuration.documents
    if type(documents) is not tuple: raise BackendError('invalid_input')
    document_definitions = [document_schema_data(s) for s in documents]
    if (documents or registers) and (_source_profile not in (None, DOCUMENT_FORMS_PROFILE, BUSINESS_PROFILE, REFERENCE_PROFILE) or INERT_SOURCE_ISSUE in configuration.activation_issues): raise BackendError('unsupported')
    if _source_profile == REFERENCE_PROFILE:
        from yadinassi.configuration.configuration_reference_profile import import_reference_configuration
        if configuration != import_reference_configuration({f.path: f.content for f in configuration.files}):
            raise BackendError('unsupported')
    if _source_profile == BUSINESS_PROFILE:
        from yadinassi.configuration.configuration_business_profile import import_business_configuration
        if configuration != import_business_configuration({f.path: f.content for f in configuration.files}):
            raise BackendError('unsupported')
    if _source_profile == DOCUMENT_FORMS_PROFILE:
        from yadinassi.configuration.configuration_document_profile import import_document_forms_configuration
        if configuration != import_document_forms_configuration({f.path: f.content for f in configuration.files}):
            raise BackendError('unsupported')
    schemas = tuple(configuration.catalogs)
    if not 1 <= len(schemas) + len(documents) + len(registers) <= 512: raise BackendError('invalid_input')
    definitions = [_schema_data(s) for s in schemas]
    section_count = sum(len(s.tabular_sections) for s in schemas)
    if section_count > _MAX_DATABASE_SECTIONS or sum(len(_json(d)) for d in definitions) > _MAX_CONFIG_BYTES:
        raise BackendError('invalid_input')
    storage_version = (10 if any(s.hierarchy != 'none' for s in schemas) else 9 if any(r.periodic for r in registers) else 8 if registers else 7 if documents else 6 if _source_profile is not None else
                       5 if INERT_SOURCE_ISSUE in configuration.activation_issues else
                       4 if any(s.numbering != 'explicit' for s in schemas) else
                       3 if section_count else 2)
    if query_indexes and storage_version == 5: raise BackendError('unsupported')
    if storage_version == 10 and (_source_profile is not None or INERT_SOURCE_ISSUE in configuration.activation_issues): raise BackendError('unsupported')
    identities = {s.identity for s in schemas}
    if len(identities) != len(schemas): raise BackendError('invalid_input')
    if any(f.target_catalog_id not in identities for s in schemas for f in _all_fields(s) if f.kind == 'catalog_ref'):
        raise BackendError('invalid_input')
    if documents:
        document_ids = {d.identity for d in documents}
        if identities & document_ids or len(document_ids) != len(documents): raise BackendError('invalid_input')
        all_ids = set()
        for schema in (*schemas,*documents):
            for item in (schema,*schema.fields,*schema.tabular_sections,*(f for sec in schema.tabular_sections for f in sec.fields)):
                if item.identity in all_ids: raise BackendError('invalid_input')
                all_ids.add(item.identity)
        if len({d.name.casefold() for d in documents}) != len(documents): raise BackendError('invalid_input')
        if any(f.target_catalog_id not in identities for d in documents for f in _all_fields(d) if f.kind == 'catalog_ref'): raise BackendError('invalid_input')
        if section_count + sum(len(d.tabular_sections) for d in documents) > _MAX_DATABASE_SECTIONS: raise BackendError('invalid_input')
        if sum(len(_json(d)) for d in (*definitions,*document_definitions)) > _MAX_CONFIG_BYTES: raise BackendError('invalid_input')
    if registers:
        validate_register_configuration(registers, schemas, documents)
        if sum(len(_json(d)) for d in (*definitions,*document_definitions,*register_definitions)) > _MAX_CONFIG_BYTES: raise BackendError('invalid_input')
    files = tuple(configuration.files)
    if not 1 <= len(files) <= _MAX_FILES or sum(len(f.content) for f in files) > _MAX_CONFIG_BYTES:
        raise BackendError('invalid_input')
    if len({f.path for f in files}) != len(files): raise BackendError('invalid_input')
    for f in files:
        if type(f.kind) is not str or f.kind not in ('xml','module'): raise BackendError('invalid_input')
        if type(f.path) is not str or len(f.path) > 256 or f.path.startswith('/') or '\\' in f.path or ':' in f.path or '\x00' in f.path or any(p in ('','.', '..') for p in f.path.split('/')) or type(f.content) is not bytes or len(f.content) > 1024*1024:
            raise BackendError('invalid_input')
    if storage_version == 6:
        from yadinassi.configuration.configuration_xml import _demo_configuration
        if configuration != _demo_configuration({f.path: f.content for f in files}, _source_profile)[0]:
            raise BackendError('unsupported')
    if storage_version == 5:
        from yadinassi.configuration.configuration_xml import import_inert_configuration
        canonical = import_inert_configuration({f.path: f.content for f in files})
        if activate or configuration != canonical:
            raise BackendError('unsupported')
    return (schemas, registers, documents, definitions, register_definitions, document_definitions, storage_version, files)

# Definition-time ABI for the direct live movement ownership traversal.
_DIRECT_MOVEMENT_PARENT_CLASSES=tuple((cls,cls.__mro__,tuple(vars(cls).items()))
    for cls in dict.fromkeys(base for receiver in (SQLiteCatalogBackend,) for base in receiver.__mro__))

# Exact source-selection entry for bounded explicit-transaction preparation.
_TRANSACTION_PREPARATION_POLICY_ABI=(SQLiteCatalogBackend,SQLiteCatalogBackend._main_demo_write_source)

# Only the ordinary writer that performs full same-lock admission may consume
# its opened-source candidate. Preserve custom selection and writer hooks.
_ORDINARY_MAIN_DEMO_WRITE_ABI = tuple((name, getattr(SQLiteCatalogBackend, name)) for name in (
    'catalog_write_preparation', '_main_demo_write_source', '_main_demo_source_snapshot',
    'begin_write', '_begin', '_validate_transaction_admission',
))

# Preserve host overrides and fault-injection adapters on the existing raw lane.
_REGISTER_OPEN_ABI = {name:getattr(SQLiteCatalogBackend,name)
                      for name in ('begin_read','begin_register_read','begin_register_write')}

# A host-overridden public read path keeps its admitted document view.
_DOCUMENT_POSTED_OPEN_ABI = {name:getattr(SQLiteCatalogBackend,name)
                             for name in ('begin_document_read','begin_read')}
