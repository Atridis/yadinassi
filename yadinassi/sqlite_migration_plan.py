"""Explicit offline additive migration plans, never an open-time upgrade.

Operators must stop all processes, retain a verified backup, and keep maintenance
in effect through apply/resolve. A SQLite lock does not exclude idle processes.
"""
from dataclasses import dataclass
import hashlib
import json
import sqlite3
from uuid import UUID, uuid4
from .catalog_backend import BackendError
from .sqlite_transaction_profile import BASE_VERSIONS, PROFILE_DDL, base_version, profile_index_ddls, validate_marker
from .sqlite_catalog_migration import _open as _legacy_open
from .sqlite_query_indexes import register_query_collations


@dataclass(frozen=True, slots=True)
class StorageMigrationPlan:
    migration_id: UUID
    database_id: UUID
    source_version: int
    target_version: int
    source_hash: str
    steps: tuple[str, ...]
    plan_hash: str


def _open(path, *, readonly):
    db = _legacy_open(path,readonly=readonly)
    try: register_query_collations(db); return db
    except BaseException:
        db.close(); raise


def _hash(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def _quote(value): return '"'+value.replace('"','""')+'"'


def _fingerprint(db, *, upgraded=False, excluded_indexes=()):
    omitted = {'transaction_profile','unit_of_work_receipt','transaction_migration'} if upgraded else set()
    tables = tuple(name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND substr(name,1,7)!='sqlite_' ORDER BY name") if name not in omitted)
    if len(tables) > 4096: raise BackendError('unsupported')
    digest = hashlib.sha256(b'yadinassi-storage-plan-v1\0'); total = 0
    for name,ddl in db.execute("SELECT name,sql FROM sqlite_master WHERE type IN ('index','view','trigger') AND sql IS NOT NULL ORDER BY name"):
        if upgraded and ddl in excluded_indexes: continue
        digest.update(name.encode());digest.update(ddl.encode());digest.update(b'\0')
    for table in tables:
        ddl = db.execute('SELECT sql FROM sqlite_master WHERE type=\'table\' AND name=?',(table,)).fetchone()[0]
        digest.update(ddl.encode()); digest.update(b'\0')
        columns = tuple(db.execute('PRAGMA table_info(%s)' % _quote(table)))
        if not 1 <= len(columns) <= 512: raise BackendError('unsupported')
        # Bound cells in SQL before returning untrusted payloads to Python.
        sizes = ['COALESCE(length(CAST(%s AS BLOB)),0)' % _quote(c[1]) for c in columns]
        if db.execute('SELECT 1 FROM %s WHERE %s LIMIT 1' % (_quote(table),' OR '.join(s+'>16777216' for s in sizes))).fetchone(): raise BackendError('unsupported')
        keys = [c[1] for c in sorted(columns,key=lambda c:c[5]) if c[5]] or [c[1] for c in columns]
        for row in db.execute('SELECT * FROM %s ORDER BY %s' % (_quote(table),','.join(_quote(k) for k in keys))):
            digest.update(b'R')
            for cell in row:
                if cell is None: tag,raw = b'0',b''
                elif type(cell) is str: tag,raw = b't',cell.encode('utf-8')
                elif type(cell) is int: tag,raw = b'i',str(cell).encode('ascii')
                elif type(cell) is bytes: tag,raw = b'b',cell
                else: raise BackendError('integrity')
                total += len(raw)
                if total > 256*1024*1024: raise BackendError('unsupported')
                digest.update(tag);digest.update(len(raw).to_bytes(8,'big'));digest.update(raw)
    return digest.hexdigest()


def _steps(version, indexes):
    return (*PROFILE_DDL,*indexes,'retain_source_profile:%d'%version,'set_format:11')


def _plan_hash(database,version,source,steps):
    return _hash(['storage_migration_v1',str(database),version,11,source,steps])


def _validate(plan):
    if (type(plan) is not StorageMigrationPlan or type(plan.migration_id) is not UUID or not plan.migration_id.int
            or type(plan.database_id) is not UUID or not plan.database_id.int or type(plan.source_version) is not int
            or plan.source_version not in BASE_VERSIONS or type(plan.target_version) is not int or plan.target_version != 11
            or type(plan.source_hash) is not str or len(plan.source_hash)!=64
            or any(c not in '0123456789abcdef' for c in plan.source_hash)
            or type(plan.steps) is not tuple or not 5 <= len(plan.steps) <= 518
            or any(type(step) is not str or len(step)>4096 for step in plan.steps)
            or plan.steps[:len(PROFILE_DDL)] != PROFILE_DDL
            or plan.steps[-2:] != ('retain_source_profile:%d'%plan.source_version,'set_format:11')
            or plan.plan_hash != _plan_hash(plan.database_id,plan.source_version,plan.source_hash,plan.steps)):
        raise BackendError('invalid_input')


def transition_status(source, target):
    """An explicit matrix, not a promise that feature versions are sequential."""
    if type(source) is not int or type(target) is not int: return 'invalid_version'
    if source in BASE_VERSIONS and target == 11: return 'additive_transaction_profile'
    if source == 1 and target == 2: return 'legacy_prepare_v1_required'
    if source == target: return 'already_target'
    if source in (5,6): return 'source_activation_profile_not_supported'
    return 'transition_not_supported'


def prepare(path, *, maintenance=False, migration_id=None):
    """Read-only dry-run; equal sources produce equal steps and plan_hash."""
    if maintenance is not True: raise BackendError('invalid_input')
    from .sqlite_catalog import SQLiteCatalogBackend
    backend = SQLiteCatalogBackend(path,read_only=True)
    try:
        version = backend.format_version
        if version not in BASE_VERSIONS: raise BackendError('unsupported')
        # Source-activation grants are bound to their exact storage profile.
        # Do not commit an additive format the grant cannot subsequently open.
        if backend.activation_issues: raise BackendError('unsupported')
        database = backend.database_id
        indexes = profile_index_ddls(version,backend._schemas,backend._layout)
        schema_version = backend._sqlite_schema_version
    finally: backend.close()
    db = _open(path,readonly=True)
    try:
        db.execute('BEGIN')
        if db.execute('PRAGMA user_version').fetchone()[0] != version or db.execute('PRAGMA schema_version').fetchone()[0] != schema_version: raise BackendError('conflict')
        if db.execute('SELECT database_uuid FROM database_info WHERE singleton=1').fetchone() != (str(database),): raise BackendError('conflict')
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone(): raise BackendError('integrity')
        source = _fingerprint(db); steps = _steps(version,indexes)
        plan = StorageMigrationPlan(uuid4() if migration_id is None else migration_id,database,version,11,source,steps,_plan_hash(database,version,source,steps))
        _validate(plan); return plan
    finally: db.close()


def apply(path, plan, *, maintenance=False):
    if maintenance is not True: raise BackendError('invalid_input')
    _validate(plan)
    # Full current profile admission, before opening the exclusive writer.
    current = prepare(path,maintenance=True,migration_id=plan.migration_id)
    if current != plan: raise BackendError('conflict')
    db = _open(path,readonly=False); committing = False
    try:
        db.execute('BEGIN EXCLUSIVE')
        if db.execute('PRAGMA user_version').fetchone()[0] != plan.source_version or _fingerprint(db) != plan.source_hash:
            raise BackendError('conflict')
        for ddl in current.steps[:-2]: db.execute(ddl)
        db.execute('INSERT INTO transaction_profile VALUES(1,?)',(plan.source_version,))
        db.execute('INSERT INTO transaction_migration VALUES(1,?,?,?)',(str(plan.migration_id),plan.source_hash,plan.plan_hash))
        if _fingerprint(db,upgraded=True,excluded_indexes=plan.steps[len(PROFILE_DDL):-2]) != plan.source_hash: raise BackendError('integrity')
        db.execute('PRAGMA user_version=11')
        committing = True; db.execute('COMMIT'); db.close(); db = None
    except BaseException as error:
        from .sqlite_catalog import _interruption
        if db is not None:
            try: db.close()
            except BaseException as cleanup:
                if _interruption(cleanup) and not _interruption(error): raise
                raise BackendError('uncertain_commit') from None
        if _interruption(error): raise
        if committing: raise BackendError('uncertain_commit') from None
        raise


def resolve(path, plan, *, maintenance=False):
    if maintenance is not True: raise BackendError('invalid_input')
    _validate(plan)
    db = None
    try:
        db = _open(path,readonly=True); db.execute('BEGIN')
        from .sqlite_catalog import _APPLICATION_ID
        if db.execute('PRAGMA application_id').fetchone()[0] != _APPLICATION_ID: return 'uncertain'
        if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone(): return 'uncertain'
        if db.execute('SELECT database_uuid FROM database_info WHERE singleton=1').fetchone() != (str(plan.database_id),): return 'uncertain'
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version == plan.source_version:
            return 'not_committed' if _fingerprint(db) == plan.source_hash else 'uncertain'
        if version != 11 or base_version(db) != plan.source_version: return 'uncertain'
        validate_marker(db)
        for ddl in PROFILE_DDL:
            name=ddl.split('(')[0].split()[-1]
            if db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(name,)).fetchone() != (ddl,): return 'uncertain'
        actual_indexes=tuple(row[0] for row in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL ORDER BY name"))
        if actual_indexes!=plan.steps[len(PROFILE_DDL):-2]: return 'uncertain'
        marker = db.execute('SELECT singleton,migration_id,source_hash,plan_hash FROM transaction_migration LIMIT 2').fetchall()
        if marker != [(1,str(plan.migration_id),plan.source_hash,plan.plan_hash)]: return 'uncertain'
        if _fingerprint(db,upgraded=True,excluded_indexes=plan.steps[len(PROFILE_DDL):-2]) != plan.source_hash: return 'uncertain'
        return 'committed'
    except (BackendError,sqlite3.Error,ValueError,TypeError,OSError): return 'uncertain'
    finally:
        if db is not None: db.close()

# Reuse the closed public storage error taxonomy, never raw SQL/path messages.
from .sqlite_catalog import _boundary
prepare = _boundary(prepare)
apply = _boundary(apply)
resolve = _boundary(resolve)
