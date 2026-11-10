"""Explicit additive transaction format, preserving its source layout profile."""
from .catalog_backend import BackendError

FORMAT_VERSION = 11
BASE_VERSIONS = (2, 3, 4, 7, 8, 9, 10)
PROFILE_DDL = (
    'CREATE TABLE transaction_profile(singleton INTEGER PRIMARY KEY CHECK(singleton=1),base_version INTEGER NOT NULL)',
    'CREATE TABLE unit_of_work_receipt(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,outcomes_json TEXT NOT NULL)',
    'CREATE TABLE transaction_migration(singleton INTEGER PRIMARY KEY CHECK(singleton=1),migration_id TEXT NOT NULL,source_hash TEXT NOT NULL,plan_hash TEXT NOT NULL)',
)


def base_version(connection):
    if connection.execute("SELECT 1 FROM transaction_profile WHERE typeof(singleton)!='integer' OR typeof(base_version)!='integer' LIMIT 1").fetchone(): raise BackendError('integrity')
    rows = connection.execute('SELECT singleton,base_version FROM transaction_profile LIMIT 2').fetchall()
    if len(rows) != 1 or rows[0][0] != 1 or type(rows[0][1]) is not int or rows[0][1] not in BASE_VERSIONS:
        raise BackendError('integrity')
    return rows[0][1]


def profile_index_ddls(version, schemas=(), layout=None):
    from .sqlite_query_indexes import catalog_query_index_ddls
    documents = ('CREATE INDEX document_query_order_v1 ON document_record(document_id,date,number,record_id)',) if version >= 7 else ()
    return documents + (catalog_query_index_ddls(schemas,layout) if layout is not None else ())


def validate_marker(connection):
    from uuid import UUID
    if connection.execute("SELECT 1 FROM transaction_migration WHERE typeof(migration_id)!='text' OR length(CAST(migration_id AS BLOB))!=36 OR typeof(source_hash)!='text' OR length(CAST(source_hash AS BLOB))!=64 OR typeof(plan_hash)!='text' OR length(CAST(plan_hash AS BLOB))!=64 LIMIT 1").fetchone(): raise BackendError('integrity')
    rows = connection.execute('SELECT singleton,migration_id,source_hash,plan_hash FROM transaction_migration LIMIT 2').fetchall()
    if len(rows) != 1 or rows[0][0] != 1: raise BackendError('integrity')
    identity,source,plan = rows[0][1:]
    if (type(identity) is not str or len(identity)!=36 or type(source) is not str or type(plan) is not str
            or len(source)!=64 or len(plan)!=64 or any(c not in '0123456789abcdef' for c in source+plan)):
        raise BackendError('integrity')
    try: parsed = UUID(identity)
    except (ValueError,TypeError): raise BackendError('integrity') from None
    if not parsed.int or str(parsed)!=identity: raise BackendError('integrity')
    return rows[0]
