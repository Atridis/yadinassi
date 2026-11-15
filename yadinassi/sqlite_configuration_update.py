"""Explicit canonical v11 configuration update planning; never invoked by open.

The immutable plan is a dry-run object, not an executable SQL list. Physical
application and historical receipt admission are separate from this planner.
"""
from dataclasses import dataclass
from uuid import UUID, uuid4

from .catalog_backend import BackendError
from .configuration_evolution import additive_delta
from .configuration_xml import import_configuration
from .sqlite_catalog_layout import Layout, _allocate, _key
from .sqlite_migration_plan import _fingerprint, _hash


@dataclass(frozen=True, slots=True)
class ConfigurationUpdatePlan:
    operation_id: UUID
    database_id: UUID
    source_generation: int
    base_profile: int
    source_hash: str
    target: object
    table_mapping: tuple
    field_mapping: tuple
    added_catalogs: tuple
    appended_fields: tuple
    plan_hash: str


def extend_layout(layout, delta, reserved):
    """Allocate only new UUIDs. Existing logical/physical names stay immutable."""
    tables, fields = dict(layout._tables), dict(layout._fields)
    used = {_key(n) for n in (*reserved, *tables.values())}
    for addition in delta.catalogs:
        schema = addition.schema
        if addition.new_catalog:
            tables[schema.identity] = _allocate('catalog_', schema.name, schema.identity, used)
        field_used = {_key(n) for (owner, _), n in fields.items() if owner == schema.identity}
        field_used.update(_key(n) for n in ('record_id', 'revision', 'code', 'description', 'deletion_mark'))
        for field in sorted(addition.appended, key=lambda f: f.identity.hex):
            fields[(schema.identity, field.identity)] = _allocate('attr_', field.name, field.identity, field_used)
    return Layout(tables, fields)


def _digest(operation, database, generation, profile, source_hash, target, tables, fields, added, appended):
    files = [[f.path, f.kind, f.content.hex()] for f in target.files]
    return _hash(['configuration_update_v1', str(operation), str(database), generation,
                  profile, source_hash, target.module_runtime, files, tables, fields,
                  [str(x) for x in added], [[str(c),[str(f) for f in fs]] for c,fs in appended]])


def prepare(path, target, *, maintenance=False, operation_id=None):
    """Bounded dry run against one pinned, fully admitted source snapshot."""
    from .sqlite_catalog import SQLiteCatalogBackend
    from .configuration_evolution import canonical
    if maintenance is not True: raise BackendError('invalid_input')
    operation = uuid4() if operation_id is None else operation_id
    if type(operation) is not UUID or not operation.int: raise BackendError('invalid_input')
    target = canonical(target)
    backend = SQLiteCatalogBackend(path, read_only=True)
    try:
        if backend.format_version != 11 or not backend.activated: raise BackendError('unsupported')
        # The admitted immutable backend snapshot is rechecked by _begin; source
        # files and every physical row below are read from that same transaction.
        view = backend.begin_read()
        try:
            db = view._connection
            count, total = db.execute("SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file").fetchone()
            if not 1 <= count <= 4096 or total > 8*1024*1024:
                raise BackendError('unsupported')
            if db.execute("SELECT 1 FROM configuration_file WHERE typeof(content)!='blob' OR length(content)>1048576 OR typeof(path)!='text' OR length(path)>256 LIMIT 1").fetchone():
                raise BackendError('integrity')
            files = {}
            for p, content, digest in db.execute('SELECT path,content,sha256 FROM configuration_file ORDER BY path'):
                import hashlib
                if type(content) is not bytes or hashlib.sha256(content).hexdigest() != digest:
                    raise BackendError('integrity')
                files[p] = content
            numbering = ('decimal_v1' if any(s.numbering == 'decimal_v1' for s in
                         (*backend._schemas, *backend._document_schemas)) else 'explicit')
            try:
                source = import_configuration(files, numbering_policy=numbering,
                                              module_runtime=target.module_runtime)
            except (TypeError, ValueError): raise BackendError('unsupported') from None
            if (source.config_uuid != target.config_uuid or
                {s.identity:s for s in source.catalogs} != {s.identity:s for s in backend._schemas} or
                source.documents != backend._document_schemas or
                source.information_registers != backend._register_schemas):
                raise BackendError('integrity')
            if db.execute('SELECT configuration_uuid,name FROM database_info WHERE singleton=1').fetchone() != (str(source.config_uuid),source.name):
                raise BackendError('integrity')
            if tuple(db.execute('SELECT path,kind FROM configuration_file ORDER BY path')) != tuple(sorted((f.path,f.kind) for f in source.files)):
                raise BackendError('integrity')
            delta = additive_delta(source, target)
            for schema in backend._schemas:
                # First whole-source validation remains mandatory; a changed
                # field or projection cannot hide corruption in old rows.
                view._validate_scan_scalars(schema.identity, schema)
            if db.execute('PRAGMA integrity_check').fetchall() != [('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():
                raise BackendError('integrity')
            reserved = tuple(n for n, in db.execute('SELECT name FROM sqlite_master')) + (
                'configuration_update', 'configuration_history', 'configuration_receipt_epoch')
            layout = extend_layout(backend._layout, delta, reserved)
            tables = tuple(sorted((str(k),v) for k,v in layout._tables.items()))
            fields = tuple(sorted((str(c),str(f),n) for (c,f),n in layout._fields.items()))
            fingerprint = _fingerprint(db)
            added=tuple(a.schema.identity for a in delta.catalogs if a.new_catalog)
            appended=tuple((a.schema.identity,tuple(f.identity for f in a.appended)) for a in delta.catalogs if not a.new_catalog)
            digest = _digest(operation, backend.database_id, view.configuration_generation,
                             backend.storage_version, fingerprint, target, tables, fields, added, appended)
            return ConfigurationUpdatePlan(operation, backend.database_id, view.configuration_generation,
                backend.storage_version, fingerprint, target, tables, fields,
                added, appended, digest)
        finally: view.close()
    finally: backend.close()


def apply(path, plan, *, maintenance=False):
    """One explicit v11-to-v12 update. Unknown commit outcomes require resolve."""
    from .sqlite_migration_plan import _open
    from .sqlite_catalog import _json, _schema_data, _encode, _View, _MAX_DATABASE_BYTES
    from .sqlite_catalog_layout import quote_identifier as q, catalog_ddl, encode_columns
    from .sqlite_query_indexes import (catalog_query_index_ddls, read_index_bundle_ddls,
                                       admit_query_indexes, _index_name, check_index_bundle_budget)
    from .sqlite_transaction_profile import profile_index_ddls
    from .sqlite_configuration_history import DDL, encode_files, digest, receipt_rows, validate
    from types import SimpleNamespace
    if type(plan) is not ConfigurationUpdatePlan: raise BackendError('invalid_input')
    current=prepare(path,plan.target,maintenance=maintenance,operation_id=plan.operation_id)
    if current!=plan: raise BackendError('conflict')
    db=_open(path,readonly=False);committing=False
    try:
        page_size=db.execute('PRAGMA page_size').fetchone()[0]
        maximum=_MAX_DATABASE_BYTES//page_size
        if db.execute('PRAGMA max_page_count=%d'%maximum).fetchone()[0]>maximum:raise BackendError('unsupported')
        # Table rebuild requires deferred whole-database FK verification. No
        # cascade/delete action is permitted during the maintenance transaction.
        db.execute('PRAGMA foreign_keys=OFF')
        db.execute('BEGIN EXCLUSIVE')
        if db.execute('PRAGMA user_version').fetchone()[0]!=11 or _fingerprint(db)!=plan.source_hash:
            raise BackendError('conflict')
        source_files={p:b for p,b in db.execute('SELECT path,content FROM configuration_file')}
        numbering='decimal_v1' if any(s.numbering=='decimal_v1' for s in (*plan.target.catalogs,*plan.target.documents)) else 'explicit'
        source=import_configuration(source_files,numbering_policy=numbering,module_runtime=plan.target.module_runtime)
        delta=additive_delta(source,plan.target)
        layout=Layout({UUID(c):n for c,n in plan.table_mapping},{(UUID(c),UUID(f)):n for c,f,n in plan.field_mapping})
        preserve_read_indexes = admit_query_indexes(db,
            profile_index_ddls(plan.base_profile, source.catalogs, layout),
            read_index_bundle_ddls(plan.base_profile, source.catalogs, layout, format_version=11))
        old_schemas={s.identity:s for s in source.catalogs}
        epochs=receipt_rows(db)
        for ddl in DDL: db.execute(ddl)
        for addition in delta.catalogs:
            schema=addition.schema;identity=str(schema.identity)
            definition=_json(_schema_data(schema))
            if addition.new_catalog:
                db.execute('INSERT INTO catalog_schema VALUES(?,?,?)',(identity,schema.name,definition))
                db.execute('INSERT INTO catalog_storage_map VALUES(?,?)',(identity,layout.table_name(schema.identity)))
            else:
                db.execute('UPDATE catalog_schema SET definition=? WHERE identity=?',(definition,identity))
            for field in addition.appended:
                db.execute('INSERT INTO catalog_field_storage_map VALUES(?,?,?)',(identity,str(field.identity),layout.field_name(schema.identity,field.identity)))
            if addition.new_catalog:
                db.execute(catalog_ddl(schema,layout))
            else:
                old=old_schemas[schema.identity];table=layout.table_name(schema.identity)
                temp='configuration_rebuild_'+schema.identity.hex
                temporary=Layout({**layout._tables,schema.identity:temp},layout._fields)
                db.execute(catalog_ddl(schema,temporary))
                columns=['record_id','revision','code','description','deletion_mark']+[layout.field_name(old.identity,f.identity) for f in old.fields]
                values=encode_columns([_encode(v,f,plan.database_id) for v,f in zip(addition.defaults,addition.appended)],
                    CatalogSchema(schema.identity,schema.name,schema.code_length,schema.description_length,addition.appended))
                select=','.join(q(c) for c in columns)+(','+','.join('?' for _ in values) if values else '')
                db.execute('INSERT INTO '+q(temp)+' SELECT '+select+' FROM '+q(table),values)
                if db.execute('SELECT COUNT(*) FROM '+q(temp)).fetchone()!=db.execute('SELECT COUNT(*) FROM '+q(table)).fetchone(): raise BackendError('integrity')
                db.execute('DROP TABLE '+q(table));db.execute('ALTER TABLE '+q(temp)+' RENAME TO '+q(table))
            # Canonical table SQL, not merely equivalent columns, is required.
            if db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?",(layout.table_name(schema.identity),)).fetchone()!=(catalog_ddl(schema,layout),):raise BackendError('integrity')
        db.execute('DELETE FROM configuration_file')
        import hashlib
        for f in plan.target.files:
            db.execute('INSERT INTO configuration_file VALUES(?,?,?,?)',(f.path,f.kind,f.content,hashlib.sha256(f.content).hexdigest()))
        db.execute('UPDATE database_info SET generation=? WHERE singleton=1',(plan.source_generation+1,))
        for ddl in catalog_query_index_ddls(plan.target.catalogs,layout):
            name=ddl.split(' ON ')[0].removeprefix('CREATE INDEX ').strip('"')
            if db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",(name,)).fetchone() is None:db.execute(ddl)
        optional = read_index_bundle_ddls(plan.base_profile, plan.target.catalogs, layout, format_version=12)
        if preserve_read_indexes:
            for ddl in optional:
                if db.execute("SELECT 1 FROM sqlite_master WHERE type='index' AND name=?", (_index_name(ddl),)).fetchone() is None:
                    db.execute(ddl)
        if admit_query_indexes(db, profile_index_ddls(plan.base_profile, plan.target.catalogs, layout), optional) != preserve_read_indexes:
            raise BackendError('integrity')
        target_files={f.path:f.content for f in plan.target.files}
        db.execute('INSERT INTO configuration_update VALUES(1,?,?,?,?,?,?,?,?,?,?)',
            (str(plan.operation_id),plan.source_hash,plan.plan_hash,plan.source_generation,plan.source_generation+1,
             numbering,plan.target.module_runtime,encode_files(source_files),digest(encode_files(target_files)),digest(epochs)))
        db.executemany('INSERT INTO configuration_receipt_epoch VALUES(?,?,?)',epochs)
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)] or db.execute('PRAGMA foreign_key_check').fetchone():raise BackendError('integrity')
        candidate=SimpleNamespace(_schemas=plan.target.catalogs,_document_schemas=plan.target.documents,
            _register_schemas=plan.target.information_registers,_layout=layout,storage_version=plan.base_profile,
            format_version=12,database_id=plan.database_id,configuration_generation=plan.source_generation+1,
            _enum_domain=None)
        validator=_View(candidate,db,None)
        for schema in plan.target.catalogs:
            validator._validated_sources.clear()
            validator._validate_scan_scalars(schema.identity,schema)
        validate(db,candidate)
        check_index_bundle_budget(db,())
        if db.execute('PRAGMA page_count').fetchone()[0]*page_size>_MAX_DATABASE_BYTES:raise BackendError('unsupported')
        db.execute('PRAGMA user_version=12')
        committing=True;db.execute('COMMIT');db.close();db=None
    except BaseException:
        if db is not None:
            try:db.close()
            except BaseException:raise BackendError('uncertain_commit') from None
        if committing:raise BackendError('uncertain_commit') from None
        raise
    from .sqlite_catalog import SQLiteCatalogBackend
    try:
        admitted=SQLiteCatalogBackend(path,read_only=True);admitted.close()
    except BaseException:raise BackendError('uncertain_commit') from None


def resolve(path, plan, *, maintenance=False):
    """Read only; never replay a partially observed update."""
    from .sqlite_migration_plan import _open
    from .sqlite_catalog import SQLiteCatalogBackend
    from .sqlite_configuration_history import metadata
    if maintenance is not True or type(plan) is not ConfigurationUpdatePlan:raise BackendError('invalid_input')
    db=None
    try:
        if _digest(plan.operation_id,plan.database_id,plan.source_generation,plan.base_profile,plan.source_hash,plan.target,plan.table_mapping,plan.field_mapping,plan.added_catalogs,plan.appended_fields)!=plan.plan_hash:return 'uncertain'
        backend=SQLiteCatalogBackend(path,read_only=True)
        try:
            if backend.database_id!=plan.database_id:return 'uncertain'
            version=backend.format_version
        finally:backend.close()
        db=_open(path,readonly=True);db.execute('BEGIN')
        if version==11:return 'not_committed' if _fingerprint(db)==plan.source_hash else 'uncertain'
        if version!=12:return 'uncertain'
        row,_=metadata(db)
        if row[:5]!=(str(plan.operation_id),plan.source_hash,plan.plan_hash,plan.source_generation,plan.source_generation+1):return 'uncertain'
        return 'committed'
    except (BackendError,ValueError,TypeError,OSError):return 'uncertain'
    finally:
        if db is not None:db.close()


from .catalog_backend import CatalogSchema
from .sqlite_catalog import _boundary
prepare=_boundary(prepare)
apply=_boundary(apply)
resolve=_boundary(resolve)


def dump_plan(plan):
    """Serialize a retained recovery plan; the caller owns durable file storage."""
    import json
    from .sqlite_configuration_history import encode_files
    if type(plan) is not ConfigurationUpdatePlan:raise BackendError('invalid_input')
    value={'schema':'configuration_update_plan_v1','operation_id':str(plan.operation_id),
           'database_id':str(plan.database_id),'source_generation':plan.source_generation,
           'base_profile':plan.base_profile,'source_hash':plan.source_hash,'plan_hash':plan.plan_hash,
           'module_runtime':plan.target.module_runtime,
           'numbering':'decimal_v1' if any(s.numbering=='decimal_v1' for s in (*plan.target.catalogs,*plan.target.documents)) else 'explicit',
           'target_files':encode_files({f.path:f.content for f in plan.target.files}),
           'table_mapping':plan.table_mapping,'field_mapping':plan.field_mapping,
           'added_catalogs':[str(x) for x in plan.added_catalogs],
           'appended_fields':[[str(c),[str(f) for f in fields]] for c,fields in plan.appended_fields]}
    raw=json.dumps(value,ensure_ascii=True,separators=(',',':'))
    if len(raw)>48*1024*1024:raise BackendError('unsupported')
    if load_plan(raw)!=plan:raise BackendError('invalid_input')
    return raw


def load_plan(raw):
    """Strict, bounded source reimport; never deserialize executable objects."""
    import json
    from .sqlite_configuration_history import decode_files
    from .sqlite_transaction_profile import BASE_VERSIONS
    if type(raw) is not str or len(raw)>48*1024*1024:raise BackendError('invalid_input')
    def pairs(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError()
            result[key]=value
        return result
    def identity(value):
        if type(value) is not str:raise ValueError()
        parsed=UUID(value)
        if not parsed.int or str(parsed)!=value:raise ValueError()
        return parsed
    try:
        v=json.loads(raw,object_pairs_hook=pairs)
        keys={'schema','operation_id','database_id','source_generation','base_profile','source_hash','plan_hash','module_runtime','numbering','target_files','table_mapping','field_mapping','added_catalogs','appended_fields'}
        if type(v) is not dict or set(v)!=keys or v['schema']!='configuration_update_plan_v1':raise ValueError()
        if type(v['source_generation']) is not int or not 1<=v['source_generation']<2**63-1:raise ValueError()
        if type(v['base_profile']) is not int or v['base_profile'] not in BASE_VERSIONS:raise ValueError()
        for key in ('source_hash','plan_hash'):
            h=v[key]
            if type(h) is not str or len(h)!=64 or any(c not in '0123456789abcdef' for c in h):raise ValueError()
        target=import_configuration(decode_files(v['target_files']),numbering_policy=v['numbering'],module_runtime=v['module_runtime'])
        from .configuration_evolution import canonical
        canonical(target)
        for key,width,maximum in (('table_mapping',2,512),('field_mapping',3,32768)):
            items=v[key]
            if type(items) is not list or len(items)>maximum:raise ValueError()
            for item in items:
                if type(item) is not list or len(item)!=width or any(type(x) is not str for x in item):raise ValueError()
                for x in item[:-1]:identity(x)
                if not item[-1] or len(item[-1].encode('utf-8'))>1024:raise ValueError()
            if len({tuple(x[:-1]) for x in items})!=len(items):raise ValueError()
        added=v['added_catalogs'];appended=v['appended_fields']
        if type(added) is not list or len(added)>512 or type(appended) is not list or len(appended)>512:raise ValueError()
        additions=[]
        for item in appended:
            if type(item) is not list or len(item)!=2 or type(item[1]) is not list or len(item[1])>64:raise ValueError()
            additions.append((identity(item[0]),tuple(identity(f) for f in item[1])))
        plan=ConfigurationUpdatePlan(identity(v['operation_id']),identity(v['database_id']),v['source_generation'],v['base_profile'],v['source_hash'],target,
            tuple(tuple(x) for x in v['table_mapping']),tuple(tuple(x) for x in v['field_mapping']),tuple(identity(x) for x in added),tuple(additions),v['plan_hash'])
        if _digest(plan.operation_id,plan.database_id,plan.source_generation,plan.base_profile,plan.source_hash,plan.target,plan.table_mapping,plan.field_mapping,plan.added_catalogs,plan.appended_fields)!=plan.plan_hash:raise ValueError()
        return plan
    except (ValueError,TypeError,KeyError,AttributeError,RecursionError):raise BackendError('invalid_input') from None
