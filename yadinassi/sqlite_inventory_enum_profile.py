"""Fresh-only typed EnumRef inventory format 16. No implicit conversion or new commit authority."""
import hashlib
import json
import os
import sqlite3
from uuid import UUID,uuid4
from .catalog_backend import BackendError
from .configuration_inventory_enums import (InventoryEnumConfiguration, canonical,
    import_inventory_enum_configuration, PROFILE)
from .enum_storage_values import EnumValueDomain
from .sqlite_accumulation_movements import ACCUMULATION_DDL,AccumulationMovementPort,schema_data
from .sqlite_document_posting_state import POSTED_DDL,POSTED_RECEIPT_DDL,read_posted

MARKER_DDL='CREATE TABLE inventory_profile(singleton INTEGER PRIMARY KEY CHECK(singleton=1),profile TEXT NOT NULL,source_digest TEXT NOT NULL)'
UNIT_DDL='CREATE TABLE unit_of_work_receipt(operation_id TEXT PRIMARY KEY,request_hash TEXT NOT NULL,outcomes_json TEXT NOT NULL)'
DDL=(MARKER_DDL,UNIT_DDL,*ACCUMULATION_DDL,POSTED_DDL,POSTED_RECEIPT_DDL)


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def _stored_uuid(value):
    try:
        parsed=UUID(value)
        if type(value) is not str or not parsed.int or str(parsed)!=value:raise ValueError()
        return parsed
    except (ValueError,TypeError,AttributeError):raise BackendError('integrity') from None


def _preflight_config(config):
    domain=EnumValueDomain(config.identity,config.enumerations)
    # Refuse deterministic storage-shape/budget failures before file allocation.
    from .sqlite_documents import schema_data as document_data,parse_schema,_MAX_TOTAL
    if len(config.files)>2048 or sum(len(raw) for _,raw in config.files)>8*1024*1024:
        raise BackendError('unsupported')
    if not config.catalogs or len(config.catalogs)+len(config.documents)+len(config.registers)>512:
        raise BackendError('unsupported')
    s=_storage()
    catalog_bytes=0
    for catalog in config.catalogs:
        raw=s._json(s._schema_data(catalog,enum_domain=domain));catalog_bytes+=len(raw.encode('utf-8'))
        if len(raw)>262144 or s._schema(raw,allow_numbering=True,enum_domain=domain)!=catalog:
            raise BackendError('unsupported')
    if catalog_bytes>s._MAX_CONFIG_BYTES:raise BackendError('unsupported')
    layout=s.build_layout(config.catalogs,reserved_names=tuple(d.split('(')[0].split()[-1] for d in (*s.DOCUMENT_DDL,*DDL)))
    s.build_section_layout(config.catalogs,layout)
    size=0
    for document in config.documents:
        raw=_storage()._json(document_data(document,enum_domain=domain));size+=len(raw.encode('utf-8'))
        if len(raw)>65536 or parse_schema(raw,enum_domain=domain)!=document:raise BackendError('unsupported')
    if size>_MAX_TOTAL or sum(len(d.tabular_sections) for d in config.documents)>512:
        raise BackendError('unsupported')
    # Only compile; stored code is never executed by create/open. The canonical
    # source grant is not permission to run module initializers or async code.
    from .document_posting_program import compile_handlers
    from .configuration_modules import MAX_ROUTINES
    from .errors import BSLError
    try:
        programs,_=compile_handlers(config)
        if sum(len(program) for program in programs.values())>MAX_ROUTINES:
            raise BackendError('unsupported')
    except (ValueError,TypeError,BSLError):
        raise BackendError('unsupported') from None


def _validate_ddl(connection, config, domain):
    # Every snapshot validates the complete closed physical vocabulary. No DDL.
    s=_storage()
    layout=s.load_layout(connection,config.catalogs)
    sections=s.load_section_layout(connection,config.catalogs,layout)
    statements=tuple(d for d in s._DDL if not d.startswith('CREATE TABLE catalog_record('))
    statements=(*statements,*s.REGISTRY_DDL,s.MIGRATION_MARKER_DDL,
                *s.SECTION_REGISTRY_DDL,*s.DOCUMENT_DDL,s._SEQUENCE_DDL,*DDL)
    expected={ddl.split('(')[0].split()[-1]:ddl for ddl in statements}
    expected.update({layout.table_name(c.identity):s.catalog_ddl(c,layout,enum_domain=domain)
                     for c in config.catalogs})
    if connection.execute("SELECT 1 FROM sqlite_master WHERE length(CAST(name AS BLOB))>1024 OR length(CAST(COALESCE(sql,'') AS BLOB))>262144 LIMIT 1").fetchone():raise BackendError('unsupported')
    count,size=connection.execute("SELECT COUNT(*),COALESCE(SUM(length(CAST(name AS BLOB))+length(CAST(COALESCE(sql,'') AS BLOB))),0) FROM sqlite_master").fetchone()
    if count>4096 or size>64*1024*1024:raise BackendError('unsupported')
    actual=dict(connection.execute("SELECT name,sql FROM sqlite_master WHERE type='table' AND lower(substr(name,1,7))!='sqlite_'"))
    if actual!=expected or connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view') LIMIT 1").fetchone():raise BackendError('integrity')
    from .sqlite_query_indexes import admit_query_indexes,read_index_bundle_ddls
    admit_query_indexes(connection,s.transaction_profile.profile_index_ddls(7,config.catalogs,layout),
        read_index_bundle_ddls(7,config.catalogs,layout,format_version=16))


def read_source(connection, *, _prepared=None):
    """Rehash current source before decoding typed schemas; no row authority."""
    if (connection.execute('PRAGMA application_id').fetchone()!=(_storage()._APPLICATION_ID,)
            or connection.execute('PRAGMA user_version').fetchone()!=(16,)):
        raise BackendError('integrity')
    if connection.execute('SELECT 1 FROM migration_marker LIMIT 1').fetchone():
        raise BackendError('integrity')
    count,size=connection.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
    if not 1<=count<=2048 or size>8*1024*1024:raise BackendError('unsupported')
    if connection.execute("SELECT 1 FROM configuration_file WHERE typeof(path)!='text' OR length(path)>256 OR typeof(content)!='blob' OR length(content)>1048576 OR typeof(sha256)!='text' OR length(sha256)!=64 LIMIT 1").fetchone():raise BackendError('integrity')
    files={};entries=[]
    for path,kind,raw,digest in connection.execute('SELECT path,kind,content,sha256 FROM configuration_file'):
        if kind!=('module' if path.endswith('.bsl') else 'xml') or hashlib.sha256(raw).hexdigest()!=digest:raise BackendError('integrity')
        files[path]=raw;entries.append((path,kind,len(raw),digest))
    marker=connection.execute('SELECT singleton,profile,source_digest FROM inventory_profile LIMIT 2').fetchall()
    from .configuration_inventory_enum_application import (
        PROFILE as UI_PROFILE, InventoryEnumApplicationConfiguration, import_inventory_application)
    if len(marker)!=1 or marker[0][0]!=1 or marker[0][1] not in (PROFILE, UI_PROFILE):
        raise BackendError('integrity')
    profile=marker[0][1]
    expected_type=InventoryEnumConfiguration if profile==PROFILE else InventoryEnumApplicationConfiguration
    info=connection.execute('SELECT database_uuid,configuration_uuid,name,generation,activated,activation_issues FROM database_info WHERE singleton=1').fetchone()
    if info is None:raise BackendError('integrity')
    database_id=_stored_uuid(info[0])
    key=('inventory-enum',database_id,
        tuple(connection.execute('PRAGMA '+name).fetchone()[0] for name in ('application_id','user_version','schema_version')),
        info,tuple(marker),tuple(sorted(entries)))
    config=_prepared.lookup(key) if _prepared is not None else None
    if config is None:
        try:config=(import_inventory_enum_configuration(files,inventory_runtime=profile) if profile==PROFILE
                    else import_inventory_application(files,inventory_runtime=profile))
        except (ValueError,TypeError):raise BackendError('integrity') from None
    if type(config) is not expected_type or config.profile!=profile:raise BackendError('integrity')
    if marker!=[(1,profile,config.source_digest)]:raise BackendError('integrity')
    if info!=(str(database_id),str(config.identity),config.name,1,1,'[]'):raise BackendError('integrity')
    domain=EnumValueDomain(database_id,config.enumerations)
    _validate_ddl(connection,config,domain)
    return config,domain,key


def admit(connection,database_id,catalogs,documents,*,validate_rows=False,_prepared=None):
    config,domain,key=read_source(connection,_prepared=_prepared)
    if domain.database_id!=database_id or config.catalogs!=catalogs or config.documents!=documents:
        raise BackendError('integrity')
    if connection.execute('SELECT COUNT(*) FROM accumulation_register_schema').fetchone()[0]!=len(config.registers):raise BackendError('integrity')
    if validate_rows:
        _preflight_config(config)
    port=AccumulationMovementPort(connection,database_id,1,config.registers,active_only=True,reference_catalogs=catalogs,enum_domain=domain)
    from .document_backend import DocumentKey
    for schema in config.registers:
        port._require(schema.identity,DocumentKey(database_id,schema.recorder_documents[0],UUID(int=1)))
    if validate_rows:
        stored_documents,_=_storage().load_document_schemas(connection,catalogs,enum_domain=domain)
        if stored_documents!=config.documents:raise BackendError('integrity')
        from .sqlite_accumulation_movements import validate_database_budget as accumulation_budget
        accumulation_budget(connection)
        if connection.execute('PRAGMA foreign_key_check').fetchone():raise BackendError('integrity')
        for reg,doc,record in connection.execute('SELECT register_id,document_id,record_id FROM accumulation_partition'):
            port.read(_stored_uuid(reg),DocumentKey(database_id,_stored_uuid(doc),_stored_uuid(record)))
        from .sqlite_document_posting_state import validate_database_budget as posted_budget
        posted_budget(connection)
        for doc,record in connection.execute('SELECT document_id,record_id FROM document_posting_state'):
            read_posted(connection,database_id,DocumentKey(database_id,_stored_uuid(doc),_stored_uuid(record)))
    if _prepared is not None:_prepared.remember(key,config)
    return config


def create(cls,path,configuration):
    # The original public core creator remains exact-core only.
    try:config=canonical(configuration)
    except (ValueError,TypeError):raise BackendError('unsupported') from None
    return _create(cls,path,config)


def create_application(cls,path,configuration):
    from .configuration_inventory_enum_application import canonical as application_canonical
    try:config=application_canonical(configuration)
    except (ValueError,TypeError):raise BackendError('unsupported') from None
    return _create(cls,path,config)


def _create(cls,path,config):
    s=_storage()
    _preflight_config(config)
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
        database_id=uuid4();domain=EnumValueDomain(database_id,config.enumerations)
        connection.execute('INSERT INTO database_info VALUES(1,?,1,?,?,1,?)',(str(database_id),str(config.identity),config.name,'[]'))
        layout=s.build_layout(config.catalogs,reserved_names=tuple(d.split('(')[0].split()[-1] for d in (*s.DOCUMENT_DDL,*DDL)))
        for catalog in config.catalogs:
            connection.execute('INSERT INTO catalog_schema VALUES(?,?,?)',
                (str(catalog.identity),catalog.name,s._json(s._schema_data(catalog,enum_domain=domain))))
        s.save_layout(connection,layout)
        s.save_section_layout(connection,s.build_section_layout(config.catalogs,layout))
        for catalog in config.catalogs:
            connection.execute(s.catalog_ddl(catalog,layout,enum_domain=domain))
            if catalog.numbering=='decimal_v1':connection.execute('INSERT INTO catalog_sequence VALUES(?,1)',(str(catalog.identity),))
        for document in config.documents:
            connection.execute('INSERT INTO document_schema VALUES(?,?,?)',(str(document.identity),document.name,s._json(s.document_schema_data(document,enum_domain=domain))))
            if document.numbering=='decimal_v1':connection.execute('INSERT INTO document_sequence VALUES(?,1)',(str(document.identity),))
        for schema in config.registers:
            connection.execute('INSERT INTO accumulation_register_schema VALUES(?,?)',(str(schema.identity),s._json(schema_data(schema,enum_domain=domain))))
            connection.executemany('INSERT INTO accumulation_register_document VALUES(?,?)',[(str(schema.identity),str(doc)) for doc in schema.recorder_documents])
        for path,content in config.files:connection.execute('INSERT INTO configuration_file VALUES(?,?,?,?)',(path,'module' if path.endswith('.bsl') else 'xml',content,hashlib.sha256(content).hexdigest()))
        connection.execute('INSERT INTO inventory_profile VALUES(1,?,?)',(config.profile,config.source_digest))
        for ddl in s.transaction_profile.profile_index_ddls(7,config.catalogs,layout):connection.execute(ddl)
        connection.execute('PRAGMA application_id=%d'%s._APPLICATION_ID);connection.execute('PRAGMA user_version=16')
        admit(connection,database_id,config.catalogs,config.documents,validate_rows=True)
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
