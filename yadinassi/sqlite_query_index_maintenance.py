"""Explicit offline installation of a closed optional read-index bundle.

Stop all application owners, retain a verified backup, and keep maintenance in
force through apply/resolve. Locks exclude active transactions, not idle owners.
No format, generation, table layout, source grant or receipt encoding changes.
"""
from dataclasses import dataclass
import hashlib
import json
import os
import sqlite3
from uuid import UUID

from .catalog_backend import BackendError
from .sqlite_query_indexes import (admit_query_indexes, canonical_index_ddls,
                                   read_index_bundle_ddls, check_index_bundle_budget)
from .sqlite_catalog_layout import quote_identifier
from .sqlite_migration_plan import _open


@dataclass(frozen=True, slots=True)
class QueryIndexPlan:
    database_id: UUID
    configuration_generation: int
    format_version: int
    schema_version: int
    file_identity: tuple[int, int]
    source_hash: str
    baseline: tuple[str, ...]
    additions: tuple[str, ...]
    plan_hash: str


def _digest(database, generation, version, schema_version, identity, source, baseline, additions):
    data = ['query_index_bundle_v1', str(database), generation, version,
            schema_version, identity, source, baseline, additions]
    return hashlib.sha256(json.dumps(data, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def _validate(plan):
    if (type(plan) is not QueryIndexPlan or type(plan.database_id) is not UUID or not plan.database_id.int
            or type(plan.configuration_generation) is not int or not 1 <= plan.configuration_generation < 2**63
            or type(plan.format_version) is not int or not 2 <= plan.format_version <= 14
            or type(plan.schema_version) is not int or not 0 <= plan.schema_version < 2**31
            or type(plan.file_identity) is not tuple or len(plan.file_identity) != 2
            or any(type(n) is not int or n < 0 for n in plan.file_identity)
            or type(plan.source_hash) is not str or len(plan.source_hash) != 64
            or any(c not in '0123456789abcdef' for c in plan.source_hash)
            or type(plan.additions) is not tuple or not plan.additions
            or canonical_index_ddls(plan.baseline) != plan.baseline
            or canonical_index_ddls(plan.additions) != plan.additions
            or plan.plan_hash != _digest(plan.database_id, plan.configuration_generation,
                plan.format_version, plan.schema_version, plan.file_identity, plan.source_hash,
                plan.baseline, plan.additions)):
        raise BackendError('invalid_input')
    canonical_index_ddls(plan.baseline + plan.additions)


def _sets(backend):
    from .sqlite_transaction_profile import profile_index_ddls
    baseline = (profile_index_ddls(backend.storage_version, backend._schemas, backend._layout)
                if backend.format_version in (11, 12, 13, 14) else ())
    optional = read_index_bundle_ddls(backend.storage_version, backend._schemas,
                                     backend._layout, format_version=backend.format_version)
    return canonical_index_ddls(baseline), optional


def _fingerprint(db, *, exclude=()):
    """Exact tables/data and explicit schema, excluding only planned index DDL.

    Unlike a format migration, this never omits profile or receipt tables. Raw
    bytes are streamed with pre-fetch cell bounds; no decode/re-encode occurs.
    """
    digest = hashlib.sha256(b'yadinassi-query-index-plan-v1\0')
    total = 0
    if db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()[0] > 4096:
        raise BackendError('unsupported')
    if db.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR "
                  "length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone():
        raise BackendError('unsupported')
    for kind, name, ddl in db.execute(
            "SELECT type,name,sql FROM sqlite_master WHERE type IN ('index','view','trigger') "
            "AND sql IS NOT NULL ORDER BY type,name"):
        if kind == 'index' and ddl in exclude: continue
        for cell in (kind, name, ddl):
            raw = cell.encode(); digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
    tables = tuple(row[0] for row in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7))!='sqlite_' ORDER BY name"))
    for table in tables:
        ddl = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()[0]
        raw = ddl.encode(); digest.update(b'T'); digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
        columns = tuple(db.execute('PRAGMA table_info(' + quote_identifier(table) + ')'))
        if not 1 <= len(columns) <= 512: raise BackendError('unsupported')
        sizes = ['COALESCE(length(CAST(' + quote_identifier(column[1]) + ' AS BLOB)),0)' for column in columns]
        if db.execute('SELECT 1 FROM ' + quote_identifier(table) + ' WHERE ' +
                      '(' + '+'.join(sizes) + ')>16777216 LIMIT 1').fetchone():
            raise BackendError('unsupported')
        keys = [column[1] for column in sorted(columns, key=lambda c: c[5]) if column[5]] or [c[1] for c in columns]
        for row in db.execute('SELECT * FROM ' + quote_identifier(table) +
                              ' ORDER BY ' + ','.join(quote_identifier(key) for key in keys)):
            digest.update(b'R')
            for cell in row:
                if cell is None: tag, raw = b'0', b''
                elif type(cell) is str: tag, raw = b't', cell.encode('utf-8')
                elif type(cell) is int: tag, raw = b'i', str(cell).encode('ascii')
                elif type(cell) is bytes: tag, raw = b'b', cell
                else: raise BackendError('integrity')
                total += len(raw)
                if total > 256 * 1024 * 1024: raise BackendError('unsupported')
                digest.update(tag); digest.update(len(raw).to_bytes(8, 'big')); digest.update(raw)
    return digest.hexdigest()


def _file_matches(path, identity):
    info = os.lstat(path)
    if (info.st_dev, info.st_ino) != identity: raise BackendError('conflict')


def prepare(path, *, maintenance=False):
    """Read-only deterministic plan for an absent optional bundle."""
    if maintenance is not True: raise BackendError('invalid_input')
    from .sqlite_catalog import SQLiteCatalogBackend
    from .sqlite_documents import DocumentView
    backend = SQLiteCatalogBackend(path, read_only=True)
    try:
        if not backend.activated or backend.storage_version in (1, 5): raise BackendError('unsupported')
        baseline, additions = _sets(backend)
        if not additions: raise BackendError('unsupported')
        view = backend.begin_read()
        try:
            db = view._connection
            if admit_query_indexes(db, baseline, additions): raise BackendError('conflict')
            check_index_bundle_budget(db,additions)
            for schema in backend._schemas:
                view._validate_scan_scalars(schema.identity, schema)
            if backend.storage_version >= 7:
                documents = DocumentView(view)
                for schema in backend._document_schemas: documents._validate_query_source(schema)
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
                raise BackendError('integrity')
            source = _fingerprint(db)
            identity = backend._check_file()
            schema_version = db.execute('PRAGMA schema_version').fetchone()[0]
            digest = _digest(backend.database_id, view.configuration_generation,
                backend.format_version, schema_version, identity, source, baseline, additions)
            plan = QueryIndexPlan(backend.database_id, view.configuration_generation,
                backend.format_version, schema_version, identity, source, baseline, additions, digest)
            _validate(plan)
            return plan
        finally: view.close()
    finally: backend.close()


def apply(path, plan, *, maintenance=False):
    """Atomically install the regenerated closed bundle, never caller SQL."""
    if maintenance is not True: raise BackendError('invalid_input')
    _validate(plan)
    current = prepare(path, maintenance=True)
    if current != plan: raise BackendError('conflict')
    db = None; committing = False
    try:
        _file_matches(path, plan.file_identity)
        db = _open(path, readonly=False)
        db.execute('BEGIN EXCLUSIVE')
        _file_matches(path, plan.file_identity)
        if (db.execute('PRAGMA user_version').fetchone() != (plan.format_version,)
                or db.execute('PRAGMA schema_version').fetchone() != (plan.schema_version,)
                or _fingerprint(db) != plan.source_hash):
            raise BackendError('conflict')
        from .sqlite_catalog import _MAX_DATABASE_BYTES
        page_size = db.execute('PRAGMA page_size').fetchone()[0]
        if db.execute('PRAGMA max_page_count=%d' % (_MAX_DATABASE_BYTES // page_size)).fetchone()[0] > _MAX_DATABASE_BYTES // page_size:
            raise BackendError('unsupported')
        check_index_bundle_budget(db,current.additions)
        for ddl in current.additions: db.execute(ddl)
        if not admit_query_indexes(db, plan.baseline, plan.additions): raise BackendError('integrity')
        if _fingerprint(db, exclude=plan.additions) != plan.source_hash: raise BackendError('integrity')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
            raise BackendError('integrity')
        _file_matches(path, plan.file_identity)
        committing = True
        db.execute('COMMIT')
        db.close(); db = None
    except BaseException as error:
        from .sqlite_catalog import _interruption
        if db is not None:
            try: db.close()
            except BaseException as cleanup:
                if _interruption(cleanup) and not _interruption(error): raise
                if _interruption(error): raise error
                raise BackendError('uncertain_commit') from None
        if _interruption(error): raise
        if committing: raise BackendError('uncertain_commit') from None
        raise


def resolve(path, plan, *, maintenance=False):
    """Classify only the exact unchanged source/target; never replay DDL.

    This proves an achieved index state, not which process installed it. A later
    data/schema change yields uncertain; there is no hidden maintenance receipt.
    """
    if maintenance is not True: raise BackendError('invalid_input')
    _validate(plan)
    from .sqlite_catalog import SQLiteCatalogBackend
    backend = None; view = None
    try:
        _file_matches(path, plan.file_identity)
        backend = SQLiteCatalogBackend(path, read_only=True)
        if (backend.database_id != plan.database_id or backend.format_version != plan.format_version
                or backend.configuration_generation != plan.configuration_generation
                or _sets(backend) != (plan.baseline, plan.additions)):
            return 'uncertain'
        view = backend.begin_read(); db = view._connection
        installed = admit_query_indexes(db, plan.baseline, plan.additions)
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
            return 'uncertain'
        if _fingerprint(db, exclude=plan.additions if installed else ()) != plan.source_hash:
            return 'uncertain'
        _file_matches(path, plan.file_identity)
        return 'committed' if installed else 'not_committed'
    except (BackendError, sqlite3.Error, ValueError, TypeError, OSError):
        return 'uncertain'
    finally:
        try:
            if view is not None: view.close()
        finally:
            if backend is not None: backend.close()


from .sqlite_catalog import _boundary
prepare = _boundary(prepare)
apply = _boundary(apply)
resolve = _boundary(resolve)
