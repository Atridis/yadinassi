"""Closed receipt-only generation history for the explicit configuration profile."""
import hashlib
import json
from .catalog_backend import BackendError
from .configuration_xml import import_configuration
from .configuration_evolution import additive_delta

FORMAT = 12
DDL = (
    'CREATE TABLE configuration_update(singleton INTEGER PRIMARY KEY CHECK(singleton=1),operation_id TEXT NOT NULL,source_hash TEXT NOT NULL,plan_hash TEXT NOT NULL,source_generation INTEGER NOT NULL,target_generation INTEGER NOT NULL,numbering TEXT NOT NULL,module_runtime TEXT,source_json TEXT NOT NULL,target_hash TEXT NOT NULL,receipt_hash TEXT NOT NULL)',
    'CREATE TABLE configuration_receipt_epoch(family TEXT NOT NULL,operation_id TEXT NOT NULL,receipt_hash TEXT NOT NULL,PRIMARY KEY(family,operation_id))',
)
MAX_HISTORY_BYTES = 40*1024*1024
MAX_RECEIPTS = 100000
TABLES = {'catalog':'commit_receipt','document':'document_commit_receipt',
          'register':'information_register_receipt','unit':'unit_of_work_receipt'}


def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=True,separators=(',',':')).encode()).hexdigest()


def encode_files(files):
    return json.dumps([[p,content.hex()] for p,content in sorted(files.items())],separators=(',',':'))


def decode_files(raw):
    if type(raw) is not str or len(raw)>MAX_HISTORY_BYTES: raise BackendError('integrity')
    items=json.loads(raw)
    if type(items) is not list or not 1<=len(items)<=2048: raise BackendError('integrity')
    files={};total=0
    for item in items:
        if type(item) is not list or len(item)!=2 or any(type(x) is not str for x in item): raise BackendError('integrity')
        path,raw=item
        if path in files or len(path)>256 or len(raw)>2*1024*1024: raise BackendError('integrity')
        content=bytes.fromhex(raw);total+=len(content)
        if total>16*1024*1024: raise BackendError('integrity')
        files[path]=content
    if encode_files(files)!=json.dumps(items,separators=(',',':')): raise BackendError('integrity')
    return files


def receipt_rows(db):
    result=[];total=0
    tables={n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for family,table in TABLES.items():
        if table not in tables:continue
        if db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0]+len(result)>MAX_RECEIPTS: raise BackendError('unsupported')
        for row in db.execute('SELECT * FROM '+table+' ORDER BY operation_id'):
            if any(type(v) is str and len(v)>16*1024*1024 for v in row):raise BackendError('unsupported')
            total+=sum(len(v.encode('utf-8')) if type(v) is str else 16 for v in row)
            if total>256*1024*1024:raise BackendError('unsupported')
            result.append((family,row[0],digest(row)))
    return tuple(sorted(result))


def metadata(db):
    if db.execute('SELECT COUNT(*) FROM configuration_update').fetchone()[0]!=1:raise BackendError('integrity')
    if db.execute('SELECT 1 FROM configuration_update WHERE length(CAST(source_json AS BLOB))>? LIMIT 1',(MAX_HISTORY_BYTES,)).fetchone():raise BackendError('integrity')
    row=db.execute('SELECT operation_id,source_hash,plan_hash,source_generation,target_generation,numbering,module_runtime,source_json,target_hash,receipt_hash FROM configuration_update WHERE singleton=1').fetchone()
    if row is None:raise BackendError('integrity')
    operation,source_hash,plan_hash,old,new,numbering,module,raw,target_hash,receipt_hash=row
    from uuid import UUID
    if type(operation) is not str or str(UUID(operation))!=operation or not UUID(operation).int:raise BackendError('integrity')
    if type(old) is not int or not 1<=old<2**63-1 or new!=old+1:raise BackendError('integrity')
    for value in (source_hash,plan_hash,target_hash,receipt_hash):
        if type(value) is not str or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise BackendError('integrity')
    source=import_configuration(decode_files(raw),numbering_policy=numbering,module_runtime=module)
    return row,source


def validate(db, backend):
    row,source=metadata(db)
    count,total=db.execute('SELECT COUNT(*),COALESCE(SUM(length(content)),0) FROM configuration_file').fetchone()
    if not 1<=count<=2048 or total>16*1024*1024:raise BackendError('integrity')
    if db.execute("SELECT 1 FROM configuration_file WHERE typeof(content)!='blob' OR length(content)>1048576 OR typeof(path)!='text' OR length(path)>256 LIMIT 1").fetchone():raise BackendError('integrity')
    files={p:content for p,content in db.execute('SELECT path,content FROM configuration_file')}
    if digest(encode_files(files))!=row[8]:raise BackendError('integrity')
    target=import_configuration(files,numbering_policy=row[5],module_runtime=row[6])
    additive_delta(source,target)
    if {s.identity:s for s in target.catalogs}!={s.identity:s for s in backend._schemas}:raise BackendError('integrity')
    if target.documents!=backend._document_schemas or target.information_registers!=backend._register_schemas:raise BackendError('integrity')
    if db.execute('SELECT generation,configuration_uuid,name FROM database_info').fetchone()!=(row[4],str(target.config_uuid),target.name):raise BackendError('integrity')
    if db.execute('SELECT COUNT(*) FROM configuration_receipt_epoch').fetchone()[0]>MAX_RECEIPTS:raise BackendError('integrity')
    epochs=tuple(db.execute('SELECT family,operation_id,receipt_hash FROM configuration_receipt_epoch ORDER BY family,operation_id'))
    if digest(epochs)!=row[9]:raise BackendError('integrity')
    # Existing old receipts stay byte-for-byte present; new receipts are allowed.
    total=0
    for family,operation,expected in epochs:
        table=TABLES.get(family)
        if table is None:raise BackendError('integrity')
        receipt=db.execute('SELECT * FROM '+table+' WHERE operation_id=?',(operation,)).fetchone()
        if receipt is None:raise BackendError('integrity')
        total+=sum(len(v.encode('utf-8')) if type(v) is str else 16 for v in receipt)
        if total>256*1024*1024 or digest(receipt)!=expected:raise BackendError('integrity')


def generation(db, family, operation, current):
    found=db.execute('SELECT receipt_hash FROM configuration_receipt_epoch WHERE family=? AND operation_id=?',(family,str(operation))).fetchone()
    if found is None:return current
    row,_=metadata(db)
    table=TABLES.get(family)
    if table is None:raise BackendError('invalid_input')
    receipt=db.execute('SELECT * FROM '+table+' WHERE operation_id=?',(str(operation),)).fetchone()
    if receipt is None or digest(receipt)!=found[0]:raise BackendError('integrity')
    return row[3]


def bind(view, family, operation):
    if view._backend.format_version!=FORMAT:return
    if view._operation_id is not None:raise BackendError('unsupported')
    epoch=generation(view._connection,family,operation,view.configuration_generation)
    if epoch==view.configuration_generation:return
    _,source=metadata(view._connection)
    view.configuration_generation=epoch
    view._historical_catalogs={s.identity:s for s in source.catalogs}
