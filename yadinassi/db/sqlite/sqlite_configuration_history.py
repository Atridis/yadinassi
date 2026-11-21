"""Source and target metadata for the explicit additive configuration update."""
import hashlib
import json
from yadinassi.db.catalog.catalog_backend import BackendError
from yadinassi.configuration.configuration_xml import import_configuration
from yadinassi.configuration.configuration_evolution import additive_delta

DDL = (
    'CREATE TABLE configuration_update(singleton INTEGER PRIMARY KEY CHECK(singleton=1),operation_id TEXT NOT NULL,source_hash TEXT NOT NULL,plan_hash TEXT NOT NULL,source_generation INTEGER NOT NULL,target_generation INTEGER NOT NULL,numbering TEXT NOT NULL,module_runtime TEXT,source_json TEXT NOT NULL,target_hash TEXT NOT NULL)',
)
MAX_HISTORY_BYTES = 40*1024*1024


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


def metadata(db):
    if db.execute('SELECT COUNT(*) FROM configuration_update').fetchone()[0]!=1:raise BackendError('integrity')
    if db.execute('SELECT 1 FROM configuration_update WHERE length(CAST(source_json AS BLOB))>? LIMIT 1',(MAX_HISTORY_BYTES,)).fetchone():raise BackendError('integrity')
    row=db.execute('SELECT operation_id,source_hash,plan_hash,source_generation,target_generation,numbering,module_runtime,source_json,target_hash FROM configuration_update WHERE singleton=1').fetchone()
    if row is None:raise BackendError('integrity')
    operation,source_hash,plan_hash,old,new,numbering,module,raw,target_hash=row
    from uuid import UUID
    if type(operation) is not str or str(UUID(operation))!=operation or not UUID(operation).int:raise BackendError('integrity')
    if type(old) is not int or not 1<=old<2**63-1 or new!=old+1:raise BackendError('integrity')
    for value in (source_hash,plan_hash,target_hash):
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
