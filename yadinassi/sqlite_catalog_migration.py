"""Explicit offline migration of an owned v1 SQLite catalog database.

The caller MUST stop every old and new process which might open the database,
including idle backend instances, and keep them stopped until all binaries have
been upgraded. SQLite locks exclude active transactions, not idle processes.
Back up and restore operationally before migration; this module never creates a
backup and must not be run on a live database. Only SQLite UTF-8 databases are
supported; UTF-16 databases are rejected before schema changes. An uncertain_commit result must
be resolved with the exact saved plan and transaction marker on a fresh
connection, never by version alone or blindly replaying the operation. Tabular parts are not implemented here.
"""
import hashlib
from itertools import zip_longest
import json
import os
from pathlib import Path
import sqlite3
import stat
from uuid import UUID, uuid4
from dataclasses import dataclass

from .catalog_backend import BackendError
from .catalog_qualifiers import validate_string
from .sqlite_catalog import (_APPLICATION_ID, _MAX_CONFIG_BYTES, _MAX_DATABASE_BYTES,
                             _MAX_FILES, _MAX_ROW_BYTES, _MAX_ROWS, _decode,
                             _private_parent, _schema)
from .sqlite_catalog_layout import (REGISTRY_DDL, MIGRATION_MARKER_DDL, build_layout, save_layout, load_layout,
                                    quote_identifier, catalog_ddl, decode_columns,
                                    encode_columns, index_ddls)

# Frozen v1 contract, independent of the current backend's creation DDL.
_V1_DDL = (
    'CREATE TABLE database_info(singleton INTEGER PRIMARY KEY CHECK(singleton=1), database_uuid TEXT NOT NULL, generation INTEGER NOT NULL CHECK(generation>0), configuration_uuid TEXT NOT NULL, name TEXT NOT NULL, activated INTEGER NOT NULL CHECK(activated IN(0,1)), activation_issues TEXT NOT NULL)',
    'CREATE TABLE configuration_file(path TEXT PRIMARY KEY, kind TEXT NOT NULL, content BLOB NOT NULL, sha256 TEXT NOT NULL)',
    'CREATE TABLE catalog_schema(identity TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, definition TEXT NOT NULL)',
    'CREATE TABLE catalog_record(catalog_id TEXT NOT NULL REFERENCES catalog_schema(identity), record_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0), code TEXT NOT NULL, description TEXT NOT NULL, deletion_mark INTEGER NOT NULL CHECK(deletion_mark IN(0,1)), values_json TEXT NOT NULL, PRIMARY KEY(catalog_id,record_id), UNIQUE(catalog_id,code))',
    'CREATE TABLE commit_receipt(operation_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL, revisions_json TEXT NOT NULL)',
)


def _canonical_uuid(value, *, allow_empty=False):
    if type(value) is not str or len(value) != 36: raise BackendError('integrity')
    try: result = UUID(value)
    except (ValueError, TypeError): raise BackendError('integrity') from None
    if str(result) != value or (not allow_empty and not result.int): raise BackendError('integrity')
    return result


def _check_source(db):
    if db.execute('PRAGMA encoding').fetchone()[0] != 'UTF-8': raise BackendError('unsupported')
    if db.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID or db.execute('PRAGMA user_version').fetchone()[0] != 1:
        raise BackendError('unsupported')
    if db.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone(): raise BackendError('unsupported')
    if db.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0] > 2048: raise BackendError('unsupported')
    expected = {sql.split('(')[0].split()[-1]: sql for sql in _V1_DDL}
    actual = {name: sql for name, sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7)) <> 'sqlite_'")}
    if actual != expected or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') OR (type='index' AND sql IS NOT NULL) LIMIT 1").fetchone():
        raise BackendError('unsupported')
    if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
        raise BackendError('integrity')
    if db.execute("SELECT 1 FROM database_info WHERE typeof(activation_issues)!='text' OR length(CAST(activation_issues AS BLOB))>262144 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))>36 OR typeof(configuration_uuid)!='text' OR length(CAST(configuration_uuid AS BLOB))>36 LIMIT 1").fetchone(): raise BackendError('integrity')
    rows = db.execute('SELECT singleton,database_uuid,generation,configuration_uuid,name,activated,activation_issues FROM database_info LIMIT 2').fetchall()
    if len(rows) != 1: raise BackendError('integrity')
    singleton, database_uuid, generation, config_uuid, name, active, issues = rows[0]
    database_id = _canonical_uuid(database_uuid); _canonical_uuid(config_uuid)
    if singleton != 1 or type(generation) is not int or not 1 <= generation < 2**63 or type(name) is not str or not 1 <= len(name) <= 128 or type(active) is not int or active not in (0, 1) or type(issues) is not str or len(issues) > 65536:
        raise BackendError('integrity')
    issue_list = json.loads(issues)
    if type(issue_list) is not list or len(issue_list) > 2048 or any(type(x) is not str or len(x) > 1024 for x in issue_list) or (active and issue_list):
        raise BackendError('integrity')
    count, size = db.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
    if not 1 <= count <= _MAX_FILES or size > _MAX_CONFIG_BYTES: raise BackendError('integrity')
    if db.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(CAST(path AS BLOB))>1024 OR typeof(kind)!='text' OR length(CAST(kind AS BLOB))>6 OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(CAST(sha256 AS BLOB))>64 LIMIT 1").fetchone(): raise BackendError('integrity')
    for path, kind, content, digest in db.execute('SELECT path,kind,content,sha256 FROM configuration_file'):
        if (type(path) is not str or len(path) > 256 or path.startswith('/') or any(c in path for c in ('\\', ':', '\x00')) or any(p in ('', '.', '..') for p in path.split('/')) or kind not in ('xml', 'module') or type(content) is not bytes or len(content) > 1024*1024 or hashlib.sha256(content).hexdigest() != digest):
            raise BackendError('integrity')
    count = db.execute('SELECT COUNT(*) FROM catalog_schema').fetchone()[0]
    if not 1 <= count <= 128: raise BackendError('integrity')
    if db.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))>36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone(): raise BackendError('integrity')
    schemas = {}
    for identity, name, definition in db.execute('SELECT identity,name,definition FROM catalog_schema'):
        schema = _schema(definition)
        if schema.tabular_sections: raise BackendError('unsupported')
        if identity != str(schema.identity) or name != schema.name: raise BackendError('integrity')
        schemas[identity] = schema
    for schema in schemas.values():
        if any(str(f.target_catalog_id) not in schemas for f in schema.fields if f.kind == 'catalog_ref'):
            raise BackendError('integrity')
    # Bound untrusted data in SQL before materializing it in Python.
    if db.execute("SELECT 1 FROM commit_receipt WHERE typeof(operation_id)!='text' OR length(CAST(operation_id AS BLOB))>36 OR typeof(request_hash)!='text' OR length(CAST(request_hash AS BLOB))>64 OR typeof(revisions_json)!='text' OR length(CAST(revisions_json AS BLOB))>? LIMIT 1", (_MAX_ROW_BYTES,)).fetchone(): raise BackendError('integrity')
    # Receipts are retained byte-for-byte; validate bounded fields without changing them.
    for operation, digest, revisions in db.execute('SELECT operation_id,request_hash,revisions_json FROM commit_receipt'):
        _canonical_uuid(operation)
        if type(digest) is not str or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest) or type(revisions) is not str or len(revisions.encode('utf-8')) > _MAX_ROW_BYTES:
            raise BackendError('integrity')
        parsed = json.loads(revisions)
        if type(parsed) is not list or len(parsed) > _MAX_ROWS: raise BackendError('integrity')
        for item in parsed:
            if type(item) is not list or len(item) != 3: raise BackendError('integrity')
            _canonical_uuid(item[0]); _canonical_uuid(item[1])
            if item[0] not in schemas or type(item[2]) is not str or not item[2].isascii() or not item[2].isdecimal() or item[2].startswith('0') or not 1 <= int(item[2]) < 2**63:
                raise BackendError('integrity')
    return database_id, schemas


def _copy_records(db, database_id, schemas, layout):
    for schema in schemas.values():
        db.execute(catalog_ddl(schema, layout))
        for ddl in index_ddls(schema, layout): db.execute(ddl)
    # All target tables now exist; deferred FKs permit forward/cyclic references.
    for identity, schema in schemas.items():
        count, size = db.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(record_id AS BLOB))+length(CAST(code AS BLOB))+length(CAST(description AS BLOB))+length(CAST(values_json AS BLOB))+32),0) FROM catalog_record WHERE catalog_id=?", (identity,)).fetchone()
        if count > _MAX_ROWS: raise BackendError('unsupported')
        bad = db.execute("SELECT 1 FROM catalog_record WHERE catalog_id=? AND (typeof(record_id)!='text' OR length(CAST(record_id AS BLOB))>36 OR typeof(revision)!='integer' OR typeof(code)!='text' OR length(CAST(code AS BLOB))>? OR typeof(description)!='text' OR length(CAST(description AS BLOB))>? OR typeof(deletion_mark)!='integer' OR typeof(values_json)!='text' OR length(CAST(values_json AS BLOB))>?) LIMIT 1", (identity,schema.code_length*4,schema.description_length*4,_MAX_ROW_BYTES*4)).fetchone()
        if bad: raise BackendError('integrity')
        table = quote_identifier(layout.table_name(schema.identity))
        fields = ','.join(quote_identifier(layout.field_name(schema.identity, f.identity)) for f in schema.fields)
        columns = 'record_id,revision,code,description,deletion_mark' + (',' + fields if fields else '')
        placeholders = ','.join('?' for _ in range(5 + len(schema.fields)))
        read_count = 0
        for rid, revision, code, description, deletion, raw in db.execute('SELECT record_id,revision,code,description,deletion_mark,values_json FROM catalog_record WHERE catalog_id=?', (identity,)):
            _canonical_uuid(rid)
            if type(revision) is not int or not 1 <= revision < 2**63 or type(code) is not str or len(code) > schema.code_length or type(description) is not str or len(description) > schema.description_length or type(deletion) is not int or deletion not in (0, 1) or type(raw) is not str or len(raw) > _MAX_ROW_BYTES or len(raw.encode('utf-8')) > _MAX_ROW_BYTES*4:
                raise BackendError('integrity')
            # Match the strict target read contract before the source table can
            # be dropped. Migration never applies assignment truncation.
            validate_string(code, schema.code_length)
            validate_string(description, schema.description_length)
            values = json.loads(raw)
            if type(values) is not list or len(values) != len(schema.fields): raise BackendError('integrity')
            for value, field in zip(values, schema.fields):
                try: _decode(value, field, database_id)
                except BackendError: raise BackendError('integrity') from None
            encoded = encode_columns(values, schema)
            if decode_columns(encoded, schema) != values: raise BackendError('integrity')
            db.execute(f'INSERT INTO {table}({columns}) VALUES({placeholders})', (rid,revision,code,description,deletion,*encoded))
            read_count += 1
        if read_count != count or db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] != count: raise BackendError('integrity')
    if db.execute('PRAGMA foreign_key_check').fetchone(): raise BackendError('integrity')


def _verify_records(db, schemas, layout):
    """Compare the physically stored target with every source row before DROP."""
    missing = object()
    for identity, schema in schemas.items():
        table = quote_identifier(layout.table_name(schema.identity))
        fields = ','.join(quote_identifier(layout.field_name(schema.identity, f.identity)) for f in schema.fields)
        columns = 'record_id,revision,code,description,deletion_mark' + (',' + fields if fields else '')
        malformed = ["typeof(record_id)!='text'", 'length(CAST(record_id AS BLOB))>36',
                     "typeof(revision)!='integer'", "typeof(code)!='text'",
                     f'length(CAST(code AS BLOB))>{schema.code_length * 4}',
                     "typeof(description)!='text'", f'length(CAST(description AS BLOB))>{schema.description_length * 4}',
                     "typeof(deletion_mark)!='integer'"]
        sizes = []
        for field in schema.fields:
            column = quote_identifier(layout.field_name(schema.identity, field.identity))
            if field.kind == 'boolean': malformed.append(f"typeof({column})!='integer'")
            elif field.kind == 'catalog_ref': malformed.append(f"({column} IS NOT NULL AND (typeof({column})!='text' OR length(CAST({column} AS BLOB))>36))")
            else:
                limit = field.qualifiers[0] * 4 if field.kind == 'string' else (41 if field.kind == 'number' else 14)
                malformed.append(f"(typeof({column})!='text' OR length(CAST({column} AS BLOB))>{limit})")
            sizes.append(f'COALESCE(length(CAST({column} AS BLOB)),0)')
        if sizes: malformed.append('(' + '+'.join(sizes) + f')>{_MAX_ROW_BYTES*4}')
        if db.execute(f'SELECT 1 FROM {table} WHERE ' + ' OR '.join(malformed) + ' LIMIT 1').fetchone():
            raise BackendError('integrity')
        source = db.execute('SELECT record_id,revision,code,description,deletion_mark,values_json FROM catalog_record WHERE catalog_id=? ORDER BY record_id', (identity,))
        target = db.execute(f'SELECT {columns} FROM {table} ORDER BY record_id')
        for old, new in zip_longest(source, target, fillvalue=missing):
            if old is missing or new is missing or old[:5] != new[:5]: raise BackendError('integrity')
            if decode_columns(new[5:], schema) != json.loads(old[5]): raise BackendError('integrity')


@dataclass(frozen=True)
class MigrationPlan:
    migration_id: UUID
    database_uuid: UUID
    source_hash: str
    layout_hash: str


def _hash_layout(layout):
    data = [sorted((str(k), v) for k, v in layout._tables.items()),
            sorted((str(k[0]), str(k[1]), v) for k, v in layout._fields.items())]
    return hashlib.sha256(json.dumps(data, ensure_ascii=True, separators=(',', ':')).encode('ascii')).hexdigest()


def _source_hash(db):
    """Hash the exact owned v1 data without materializing entire tables."""
    digest = hashlib.sha256(b'yadinassi-sqlite-v1-plan\0')
    # Limits apply to the database file as a whole, not the scan memory limit.
    # SQL predicates run before Python receives arbitrary-length values.
    malformed = db.execute("SELECT 1 FROM catalog_record WHERE typeof(catalog_id)!='text' OR length(CAST(catalog_id AS BLOB))>36 OR typeof(record_id)!='text' OR length(CAST(record_id AS BLOB))>36 OR typeof(revision)!='integer' OR typeof(code)!='text' OR length(CAST(code AS BLOB))>4096 OR typeof(description)!='text' OR length(CAST(description AS BLOB))>4096 OR typeof(deletion_mark)!='integer' OR typeof(values_json)!='text' OR length(CAST(values_json AS BLOB))>? LIMIT 1", (_MAX_ROW_BYTES*4,)).fetchone()
    if malformed: raise BackendError('integrity')
    tables = (('database_info', 'singleton'), ('configuration_file', 'path'),
              ('catalog_schema', 'identity'), ('catalog_record', 'catalog_id,record_id'),
              ('commit_receipt', 'operation_id'))
    total = 0
    for table, order in tables:
        digest.update(table.encode('ascii') + b'\0')
        for row in db.execute(f'SELECT * FROM {table} ORDER BY {order}'):
            digest.update(b'R')
            for value in row:
                if value is None: tag, raw = b'0', b''
                elif type(value) is int: tag, raw = b'i', str(value).encode('ascii')
                elif type(value) is str: tag, raw = b't', value.encode('utf-8')
                elif type(value) is bytes: tag, raw = b'b', value
                else: raise BackendError('integrity')
                total += len(raw)
                if total > _MAX_DATABASE_BYTES: raise BackendError('unsupported')
                digest.update(tag); digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
    return digest.hexdigest()


def _open(path, *, readonly):
    raw = os.fspath(path)
    if type(raw) is not str or not raw or '\x00' in raw or raw.startswith(('file:', '//', '\\\\')): raise BackendError('invalid_input')
    absolute = _private_parent(os.path.abspath(raw))
    info = os.lstat(absolute)
    if not stat.S_ISREG(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400 or info.st_nlink != 1 or info.st_size > _MAX_DATABASE_BYTES: raise BackendError('invalid_input')
    db = sqlite3.connect(Path(absolute).as_uri() + ('?mode=ro' if readonly else '?mode=rw'), uri=True, isolation_level=None, detect_types=0, timeout=0.2)
    try:
        db.execute('PRAGMA foreign_keys=ON'); db.execute('PRAGMA trusted_schema=OFF')
        if not readonly: db.execute('PRAGMA synchronous=FULL')
        if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1 or db.execute('PRAGMA journal_mode').fetchone()[0].lower() != 'delete': raise BackendError('unsupported')
        return db
    except BaseException:
        try: db.close()
        except BaseException: raise BackendError('storage_error') from None
        raise


def _plan_data(db):
    database_id, schemas = _check_source(db)
    reserved = [row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE lower(substr(name,1,7)) <> 'sqlite_'")]
    layout = build_layout(schemas.values(), reserved_names=reserved)
    return database_id, schemas, layout, _source_hash(db), _hash_layout(layout)


def _valid_plan(plan):
    if type(plan) is not MigrationPlan or type(plan.migration_id) is not UUID or not plan.migration_id.int or type(plan.database_uuid) is not UUID or not plan.database_uuid.int or any(type(value) is not str or len(value) != 64 or any(c not in '0123456789abcdef' for c in value) for value in (plan.source_hash,plan.layout_hash)):
        raise BackendError('invalid_input')


def prepare_v1(path, *, maintenance=False):
    """Create a plan under caller-enforced maintenance; persist it externally."""
    if maintenance is not True: raise BackendError('invalid_input')
    db = None
    try:
        db = _open(path, readonly=True); db.execute('BEGIN')
        database_id, schemas, layout, source_hash, layout_hash = _plan_data(db)
        return MigrationPlan(uuid4(), database_id, source_hash, layout_hash)
    except BackendError: raise
    except sqlite3.Error: raise BackendError('storage_error') from None
    except (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError): raise BackendError('integrity') from None
    finally:
        if db is not None:
            try: db.close()
            except BaseException: raise BackendError('storage_error') from None


def migrate_v1(path, plan, *, maintenance=False):
    """Atomically upgrade v1; caller must exclude all old and new processes."""
    if maintenance is not True: raise BackendError('invalid_input')
    _valid_plan(plan)
    db = None
    transaction_started = False
    commit_started = False
    commit_returned = False
    failure = None
    try:
        db = _open(path, readonly=False)
        page_size = db.execute('PRAGMA page_size').fetchone()[0]
        try: db.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError: raise BackendError('busy') from None
        transaction_started = True
        db.execute('PRAGMA max_page_count=%d' % (_MAX_DATABASE_BYTES // page_size))
        database_id, schemas, layout, source_hash, layout_hash = _plan_data(db)
        if (database_id,source_hash,layout_hash) != (plan.database_uuid,plan.source_hash,plan.layout_hash): raise BackendError('conflict')
        for ddl in REGISTRY_DDL: db.execute(ddl)
        save_layout(db, layout)
        db.execute(MIGRATION_MARKER_DDL)
        _copy_records(db, database_id, schemas, layout)
        _verify_records(db, schemas, layout)
        db.execute('DROP TABLE catalog_record')
        db.execute('INSERT INTO migration_marker VALUES(1,?,?,?,?)', (str(plan.migration_id), str(plan.database_uuid), plan.source_hash, plan.layout_hash))
        db.execute('PRAGMA user_version=2')
        # From this point on even an error returned by close cannot prove the
        # transaction outcome. The saved marker must be resolved separately.
        commit_started = True
        db.execute('COMMIT')
        commit_returned = True
    except BaseException as exc:
        if commit_started: failure = BackendError('uncertain_commit')
        elif isinstance(exc, BackendError): failure = exc
        elif isinstance(exc, sqlite3.Error): failure = BackendError('storage_error')
        elif isinstance(exc, (OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError)): failure = BackendError('integrity')
        else: failure = exc
    finally:
        if db is not None:
            if transaction_started and not commit_returned:
                try: db.execute('ROLLBACK')
                except BaseException:
                    # A failed cleanup is not safely reported as an ordinary
                    # validation failure, and never masks uncertain COMMIT.
                    failure = BackendError('uncertain_commit')
            try: db.close()
            except BaseException:
                failure = BackendError('uncertain_commit')
    if failure is not None: raise failure from None


def resolve_migration(path, plan, *, maintenance=False):
    """Resolve an uncertain commit against the exact durable transaction marker.

    Inaccessible, changed, or inconsistent databases remain uncertain. Continued
    maintenance (including no restore/replacement) is required throughout.
    This resolver is read-only; a hot journal requiring writable SQLite recovery
    remains uncertain until the operator performs maintenance recovery.
    """
    if maintenance is not True: raise BackendError('invalid_input')
    _valid_plan(plan)
    db = None
    try:
        db = _open(path, readonly=True); db.execute('BEGIN')
        if db.execute('PRAGMA encoding').fetchone()[0] != 'UTF-8': return 'uncertain'
        if db.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID: return 'uncertain'
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == 1:
            database_id, schemas, layout, source_hash, layout_hash = _plan_data(db)
            return 'not_committed' if (database_id,source_hash,layout_hash) == (plan.database_uuid,plan.source_hash,plan.layout_hash) else 'uncertain'
        if version != 2: return 'uncertain'
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone(): return 'uncertain'
        if db.execute("SELECT 1 FROM database_info WHERE typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))!=36 LIMIT 1").fetchone(): return 'uncertain'
        row = db.execute('SELECT database_uuid FROM database_info WHERE singleton=1').fetchone()
        if row != (str(plan.database_uuid),): return 'uncertain'
        if db.execute("SELECT 1 FROM migration_marker WHERE typeof(migration_id)!='text' OR length(CAST(migration_id AS BLOB))!=36 OR typeof(database_uuid)!='text' OR length(CAST(database_uuid AS BLOB))!=36 OR typeof(source_hash)!='text' OR length(CAST(source_hash AS BLOB))!=64 OR typeof(layout_hash)!='text' OR length(CAST(layout_hash AS BLOB))!=64 LIMIT 1").fetchone(): return 'uncertain'
        rows = db.execute('SELECT singleton,migration_id,database_uuid,source_hash,layout_hash FROM migration_marker LIMIT 2').fetchall()
        if rows != [(1,str(plan.migration_id),str(plan.database_uuid),plan.source_hash,plan.layout_hash)]: return 'uncertain'
        count = db.execute('SELECT COUNT(*) FROM catalog_schema').fetchone()[0]
        if not 1 <= count <= 128: return 'uncertain'
        if db.execute("SELECT 1 FROM catalog_schema WHERE typeof(identity)!='text' OR length(CAST(identity AS BLOB))!=36 OR typeof(name)!='text' OR length(CAST(name AS BLOB))>512 OR typeof(definition)!='text' OR length(CAST(definition AS BLOB))>262144 LIMIT 1").fetchone(): return 'uncertain'
        rows = db.execute('SELECT identity,name,definition FROM catalog_schema LIMIT 129').fetchall()
        if len(rows) != count: return 'uncertain'
        schemas = tuple(_schema(definition) for _, _, definition in rows)
        if any(schema.tabular_sections for schema in schemas): return 'uncertain'
        if any((identity, name) != (str(schema.identity), schema.name) for (identity, name, _), schema in zip(rows, schemas)): return 'uncertain'
        ids = {s.identity for s in schemas}
        if len(ids) != count or any(f.target_catalog_id not in ids for s in schemas for f in s.fields if f.kind == 'catalog_ref'): return 'uncertain'
        layout = load_layout(db, schemas)
        if _hash_layout(layout) != plan.layout_hash: return 'uncertain'
        expected = {ddl.split('(')[0].split()[-1]: ddl for ddl in _V1_DDL if not ddl.startswith('CREATE TABLE catalog_record(')}
        expected.update({ddl.split('(')[0].split()[-1]: ddl for ddl in (*REGISTRY_DDL, MIGRATION_MARKER_DDL)})
        for schema in schemas: expected[layout.table_name(schema.identity)] = catalog_ddl(schema, layout)
        if db.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone() or db.execute('SELECT COUNT(*) FROM sqlite_master').fetchone()[0] > 2048: return 'uncertain'
        actual = {name: sql for name,sql in db.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7)) <> 'sqlite_'")}
        if actual != expected or db.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') OR (type='index' AND sql IS NOT NULL) LIMIT 1").fetchone(): return 'uncertain'
        return 'committed'
    except (BackendError, sqlite3.Error, OSError, ValueError, TypeError, KeyError, IndexError, OverflowError, RecursionError):
        return 'uncertain'
    finally:
        if db is not None:
            try: db.close()
            except BaseException: return 'uncertain'
