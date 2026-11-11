"""Fresh-only format 13. No implicit conversion and no migration-marker fiction."""
import hashlib
import json
import os
import sqlite3
from uuid import UUID,uuid4
from .catalog_backend import BackendError
from .configuration_posting import canonical,import_posting_configuration,PROFILE
from .sqlite_recorder_movements import RECORDER_DDL,RecorderMovementPort,schema_data
from .sqlite_document_posting_state import POSTED_DDL,POSTED_RECEIPT_DDL,read_posted

MARKER_DDL='CREATE TABLE posting_profile(singleton INTEGER PRIMARY KEY CHECK(singleton=1),profile TEXT NOT NULL,source_digest TEXT NOT NULL)'
UNIT_DDL='CREATE TABLE unit_of_work_receipt(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,outcomes_json TEXT NOT NULL)'
DDL=(MARKER_DDL,UNIT_DDL,*RECORDER_DDL,POSTED_DDL,POSTED_RECEIPT_DDL)


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def admit(connection,database_id,documents,*,validate_rows=False):
    count,size=connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
    if not 1<=count<=4096 or size>8*1024*1024:raise BackendError('unsupported')
    if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(path)>256 OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(sha256)!=64 LIMIT 1").fetchone():raise BackendError('integrity')
    files={}
    for path,kind,raw,digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file'):
        if kind!=('module' if path.endswith('.bsl') else 'xml') or hashlib.sha256(raw).hexdigest()!=digest:raise BackendError('integrity')
        files[path]=raw
    try:config=import_posting_configuration(files,posting_runtime=PROFILE)
    except (ValueError,TypeError):raise BackendError('integrity') from None
    marker=connection.execute('SELECT singleton,profile,source_digest FROM posting_profile LIMIT 2').fetchall()
    if marker!=[(1,PROFILE,config.source_digest)] or config.documents!=documents:raise BackendError('integrity')
    info=connection.execute('SELECT configuration_uuid,name,generation,activated,activation_issues FROM database_info WHERE singleton=1').fetchone()
    if info!=(str(config.identity),config.name,1,1,'[]'):raise BackendError('integrity')
    if connection.execute('SELECT COUNT(*) FROM recorder_register_schema').fetchone()[0]!=len(config.registers):raise BackendError('integrity')
    port=RecorderMovementPort(connection,database_id,1,config.registers)
    from .document_backend import DocumentKey
    for schema in config.registers:
        port._require(schema.identity,DocumentKey(database_id,schema.recorder_documents[0],UUID(int=1)))
    if validate_rows:
        from .sqlite_recorder_movements import validate_database_budget as recorder_budget
        recorder_budget(connection)
        if connection.execute('PRAGMA foreign_key_check').fetchone():raise BackendError('integrity')
        for reg,doc,record in connection.execute('SELECT register_id,document_id,record_id FROM recorder_partition'):
            port.read(UUID(reg),DocumentKey(database_id,UUID(doc),UUID(record)))
        from .sqlite_document_posting_state import validate_database_budget as posted_budget
        posted_budget(connection)
        for doc,record in connection.execute('SELECT document_id,record_id FROM document_posting_state'):
            read_posted(connection,database_id,DocumentKey(database_id,UUID(doc),UUID(record)))
    return config


def create(cls,path,configuration):
    s=_storage()
    try:config=canonical(configuration)
    except (ValueError,TypeError):raise BackendError('unsupported') from None
    raw=os.fspath(path)
    if type(raw) is not str or raw.startswith(('file:','//','\\\\')) or '\x00' in raw:raise BackendError('invalid_input')
    absolute=s._private_parent(os.path.abspath(raw));connection=None;committing=False
    try:fd=os.open(absolute,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(fd)
    except OSError:raise BackendError('storage_error') from None
    try:
        connection=sqlite3.connect(absolute,isolation_level=None,detect_types=0)
        s.register_query_collations(connection)
        connection.execute('PRAGMA foreign_keys=ON');connection.execute('PRAGMA trusted_schema=OFF');connection.execute('PRAGMA journal_mode=DELETE');connection.execute('PRAGMA synchronous=FULL')
        page=connection.execute('PRAGMA page_size').fetchone()[0];connection.execute('PRAGMA max_page_count=%d'%(s._MAX_DATABASE_BYTES//page))
        connection.execute('BEGIN IMMEDIATE')
        statements=tuple(d for d in s._DDL if not d.startswith('CREATE TABLE catalog_record('))
        for ddl in (*statements,*s.REGISTRY_DDL,s.MIGRATION_MARKER_DDL,*s.SECTION_REGISTRY_DDL,*s.DOCUMENT_DDL,s._SEQUENCE_DDL,*DDL):connection.execute(ddl)
        database_id=uuid4()
        connection.execute('INSERT INTO database_info VALUES(1,?,1,?,?,1,?)',(str(database_id),str(config.identity),config.name,'[]'))
        layout=s.build_layout((),reserved_names=tuple(d.split('(')[0].split()[-1] for d in (*s.DOCUMENT_DDL,*DDL)))
        s.save_layout(connection,layout);s.save_section_layout(connection,s.build_section_layout((),layout))
        for document in config.documents:
            connection.execute('INSERT INTO document_schema VALUES(?,?,?)',(str(document.identity),document.name,s._json(s.document_schema_data(document))))
            if document.numbering=='decimal_v1':connection.execute('INSERT INTO document_sequence VALUES(?,1)',(str(document.identity),))
        for schema in config.registers:
            connection.execute('INSERT INTO recorder_register_schema VALUES(?,?)',(str(schema.identity),s._json(schema_data(schema,database_id))))
            connection.executemany('INSERT INTO recorder_register_document VALUES(?,?)',[(str(schema.identity),str(doc)) for doc in schema.recorder_documents])
        for path,content in config.files:connection.execute('INSERT INTO configuration_file VALUES(?,?,?,?)',(path,'module' if path.endswith('.bsl') else 'xml',content,hashlib.sha256(content).hexdigest()))
        connection.execute('INSERT INTO posting_profile VALUES(1,?,?)',(PROFILE,config.source_digest))
        for ddl in s.transaction_profile.profile_index_ddls(7,(),layout):connection.execute(ddl)
        connection.execute('PRAGMA application_id=%d'%s._APPLICATION_ID);connection.execute('PRAGMA user_version=13')
        admit(connection,database_id,config.documents,validate_rows=True)
        committing=True;connection.execute('COMMIT');connection.close();connection=None
        return cls(absolute)
    except BaseException as error:
        if connection is not None:
            try:
                if connection.in_transaction:connection.execute('ROLLBACK')
            except BaseException as cleanup_error:
                if s._interruption(cleanup_error) and not s._interruption(error):error=cleanup_error
            try:connection.close()
            except BaseException as cleanup_error:
                if s._interruption(cleanup_error) and not s._interruption(error):error=cleanup_error
        if committing and not s._interruption(error):raise BackendError('uncertain_commit') from None
        raise error
