"""Host-owned ordered multi-port staging with one durable commit boundary."""
from contextlib import contextmanager
import hashlib
import json
from uuid import UUID, uuid5
from .catalog_backend import BackendError, CatalogWriteOutcome, Revision
from .catalog_qualifiers import normalize_string
from .transaction_backend import TransactionRequest, StagedTicket, TransactionOutcome
from .sqlite_documents import DocumentView, _receipt_hash
from .sqlite_registers import RegisterView

MAX_OPERATIONS = 256
MAX_BYTES = 16 * 1024 * 1024
KINDS = ('catalog_create','catalog_update','document_create','document_update',
         'register_write','register_delete','register_set','recorder_replace','accumulation_replace','document_set_posted')


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def _json(value): return _storage()._json(value)
def _hash(value): return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()
def _child(operation, index): return uuid5(operation, 'unit-of-work-v1:%d' % index)


def _recorder_port(view):
    # Absent until a future explicit canonical profile admits recorder schemas.
    # No table discovery or implicit activation on legacy v11/v12 databases.
    schemas=getattr(view._backend,'_recorder_schemas',None)
    if type(schemas) is not tuple or not schemas:raise BackendError('unsupported')
    from .sqlite_recorder_movements import RecorderMovementPort
    return RecorderMovementPort(view._connection,view.database_id,view.configuration_generation,schemas)


def _accumulation_port(view):
    # Separate canonical source profile, never inferred from table existence.
    schemas=getattr(view._backend,'_accumulation_schemas',None)
    if type(schemas) is not tuple or not schemas:raise BackendError('unsupported')
    from .sqlite_accumulation_movements import AccumulationMovementPort
    return AccumulationMovementPort(view._connection,view.database_id,view.configuration_generation,schemas,
                                    active_only=True, reference_catalogs=(view._backend._schemas
                                        if view._backend.format_version in (15,16) else ()),
                                    enum_domain=view._backend._enum_domain)


def _posting_port(view):
    return _accumulation_port(view) if view._backend.format_version in (14,15,16) else _recorder_port(view)


def _describe(view, request):
    if type(request) is not TransactionRequest or request.kind not in KINDS:
        raise BackendError('invalid_input')
    kind,draft,expected = request.kind,request.draft,request.expected
    if kind=='document_set_posted':
        if expected is not None:raise BackendError('invalid_input')
        port=_posting_port(view)
        from .sqlite_document_posting_state import describe_posted
        described=describe_posted(view.database_id,view.configuration_generation,draft)
        if draft.recorder.document_id not in {d for schema in port.schemas.values() for d in schema.recorder_documents}:raise BackendError('unsupported')
        return described
    if kind in ('recorder_replace','accumulation_replace'):
        if expected is not None:raise BackendError('invalid_input')
        port=_recorder_port(view) if kind=='recorder_replace' else _accumulation_port(view)
        return port.describe(draft)
    if kind.endswith('_create') and expected is not None: raise BackendError('invalid_input')
    if kind.endswith('_update') and expected is None: raise BackendError('invalid_input')
    if kind.startswith('catalog_'):
        draft,values = view._draft(draft); sections = view._draft_sections(draft)
        if expected is not None and (type(expected) is not Revision or (expected.database_id,expected.configuration_generation,expected.catalog_id,expected.record_id)!=(view.database_id,view.configuration_generation,draft.key.catalog_id,draft.key.record_id)): raise BackendError('conflict')
        revision = 1 if expected is None else _storage()._revision_number(expected.token)+1
        intent = _storage()._intent(draft,revision,values,sections,
                     hierarchy=view.catalog_schema(draft.key.catalog_id).hierarchy != 'none')
        identity = ('catalog',draft.key.catalog_id,draft.key.record_id)
        return _hash(intent), len(_json(intent).encode('utf-8')), identity
    if kind.startswith('document_'):
        port = DocumentView(view)
        _,intent,digest = port._intent(draft,expected)
        return digest,len(_json(intent).encode('utf-8')),('document',draft.key.document_id,draft.key.record_id)
    port = RegisterView(view)
    if kind == 'register_set':
        if expected is not None: raise BackendError('invalid_input')
        schema,rows,digest = port._set_intent(draft)
        _,wanted = port._filter_values(schema,draft.filters)
        intent = ['register_set_v1',str(schema.identity),[[str(f.identity),wanted[f.identity]] for f in schema.key_fields if f.identity in wanted],rows,draft.replace,draft.expected_snapshot]
        size = len(_json(intent).encode('utf-8'))
    else:
        schema,raw,values,digest = port._intent(draft,expected,kind == 'register_delete')
        intent = ['register_write_v1',str(schema.identity),raw,values,None if expected is None else expected.token,kind == 'register_delete']
        size = len(_json(intent).encode('utf-8'))
    # One mutation per register prevents overlapping set/single-key intents.
    return digest,size,('register',schema.identity)


def _require_staged_document(intent,requests,bindings):
    # A state transition never bypasses the document CAS/write in this batch.
    for request,binding in zip(requests,bindings):
        if request.kind not in ('document_create','document_update'):continue
        if request.draft.key!=intent.recorder:continue
        document,record,revision,_=_json_document_payload(binding[4])
        if (document,record,revision)==(str(intent.recorder.document_id),str(intent.recorder.record_id),intent.document_revision):return
    raise BackendError('conflict')


class UnitOfWork:
    """Explicit commit only. A ticket proves staging, not persistent success."""
    def __init__(self, view):
        self._view = view; self.operation_id = view._operation_id
        self._requests = (); self._results = (); self._bindings = (); self._identities = frozenset()
        self._bytes = 0; self.state = 'open'; self._savepoint_depth=0

    @property
    def requests(self): return self._requests

    def _open(self):
        if self.state != 'open': raise BackendError('closed')
        self._view._require(True)

    def stage(self, request):
        self._open()
        if len(self._requests) >= MAX_OPERATIONS: raise BackendError('unsupported')
        view = self._view
        digest,size,identity = _describe(view,request)
        if identity in self._identities and request.kind not in ('recorder_replace','accumulation_replace'): raise BackendError('unsupported')
        if self._bytes + size > MAX_BYTES: raise BackendError('unsupported')
        index = len(self._requests); child = _child(self.operation_id,index)
        kind,draft,expected = request.kind,request.draft,request.expected
        if kind=='document_set_posted':_require_staged_document(draft,self._requests,self._bindings)
        tables=['commit_receipt','unit_of_work_receipt']
        if view._backend.storage_version >= 7: tables.append('document_commit_receipt')
        if view._backend.storage_version >= 8: tables.append('information_register_receipt')
        if getattr(view._backend,'_recorder_schemas',None):tables.extend(('recorder_movement_receipt','document_posting_receipt'))
        if getattr(view._backend,'_accumulation_schemas',None):tables.extend(('accumulation_movement_receipt','document_posting_receipt'))
        if any(view._connection.execute('SELECT 1 FROM '+table+' WHERE operation_id=?',(str(child),)).fetchone() for table in tables): raise BackendError('conflict')
        # Outer savepoint includes child receipt, state allocation and every
        # underlying mutation; failed staging never leaves a receipt orphan.
        with view._atomic_record():
            if kind.startswith('catalog_'):
                if expected is None: view.create(draft)
                else: view.update(draft,expected)
                result = view._outcomes[-1]
                modern = view._backend.storage_version in (4,7,8,9,10)
                bound = _storage()._receipt_digest([view._intents[-1]],[result] if modern else None)
                r = result.revision
                entry = [str(r.catalog_id),str(r.record_id),r.token]
                if modern: entry.append(result.code)
                payload = _json([entry])
                view._connection.execute('INSERT INTO commit_receipt VALUES(?,?,?)',(str(child),bound,payload))
            elif kind=='document_set_posted':
                from .sqlite_document_posting_state import write_posted_receipt
                result,bound,payload=write_posted_receipt(view._connection,view.database_id,view.configuration_generation,child,draft)
            elif kind.startswith('document_'):
                port = DocumentView(view)
                if expected is None: port.create(draft)
                else: port.update(draft,expected)
                result = port._outcome; r = result.revision
                bound = _receipt_hash(port._hash,result)
                payload = _json([str(r.document_id),str(r.record_id),r.token,result.number])
                view._connection.execute('INSERT INTO document_commit_receipt VALUES(?,?,?,?,?,?)',
                    (str(child),bound,str(r.document_id),str(r.record_id),int(r.token),result.number))
            elif kind=='recorder_replace':
                result=_recorder_port(view).replace(child,draft)
                bound,payload=view._connection.execute('SELECT request_hash,outcome_json FROM recorder_movement_receipt WHERE operation_id=?',(str(child),)).fetchone()
            elif kind=='accumulation_replace':
                result=_accumulation_port(view).replace(child,draft)
                bound,payload=view._connection.execute('SELECT request_hash,outcome_json FROM accumulation_movement_receipt WHERE operation_id=?',(str(child),)).fetchone()
            else:
                port = RegisterView(view)
                if kind == 'register_set': port.write_set(draft)
                elif kind == 'register_delete': port.delete(draft,expected)
                else: port.write(draft,expected)
                result = port._outcome; payload = _json(port._outcome_data(result))
                bound = hashlib.sha256((port._digest+payload).encode()).hexdigest()
                view._connection.execute('INSERT INTO information_register_receipt VALUES(?,?,?)',(str(child),bound,payload))
            ticket = StagedTicket(self.operation_id,index,kind)
            requests = (*self._requests,request)
            results = (*self._results,TransactionOutcome(ticket,result))
            bindings = (*self._bindings,(kind,str(child),digest,bound,payload))
            identities = self._identities | {identity}
            total = self._bytes+size
            if total + len(_json(bindings).encode('utf-8')) > MAX_BYTES: raise BackendError('unsupported')
        self._requests,self._results,self._bindings,self._identities,self._bytes = requests,results,bindings,identities,total
        return ticket

    @contextmanager
    def savepoint(self):
        """Rollback one host operation and journal; keep earlier root stages."""
        self._open()
        if self._savepoint_depth>=32:raise BackendError('unsupported')
        before=(self._requests,self._results,self._bindings,self._identities,self._bytes)
        self._savepoint_depth+=1
        try:
            with self._view._atomic_record():yield self
        except BaseException:
            self._requests,self._results,self._bindings,self._identities,self._bytes=before
            raise
        finally:self._savepoint_depth-=1

    def read_document_posted(self,key):
        self._open();_posting_port(self._view)
        from .sqlite_document_posting_state import read_posted
        return read_posted(self._view._connection,self._view.database_id,key)

    def read_recorder(self,register_id,key):
        self._open();return _recorder_port(self._view).read(register_id,key)

    def read_accumulation(self,register_id,key):
        self._open();return _accumulation_port(self._view).read(register_id,key)

    def read_catalog(self, key):
        self._open(); return self._view.read_catalog(key)

    def read_document(self, key):
        self._open(); return DocumentView(self._view).read_document(key)

    def read_register(self, key):
        self._open(); return RegisterView(self._view).read_record(key)

    def commit(self):
        self._open()
        if self._savepoint_depth:raise BackendError('unsupported')
        if not self._requests: raise BackendError('invalid_input')
        encoded = _json(self._bindings)
        digest = _hash(['unit_of_work_v1',str(self._view.database_id),self._view.configuration_generation,
                        [row[:3] for row in self._bindings],encoded])
        # Allocation/encoding failures above are pre-commit failures.
        self.state = 'committing'
        try:
            self._view._connection.execute('INSERT INTO unit_of_work_receipt VALUES(?,?,?)',
                                          (str(self.operation_id),digest,encoded))
            self._view._connection.execute('COMMIT')
            self._view.close()
        except BaseException as error:
            self.state = 'uncertain'
            try: self._view.close()
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            if _storage()._interruption(error): raise
            raise BackendError('uncertain_commit') from None
        self.state = 'committed'
        return self._results

    def rollback(self):
        try: self._view.close()
        finally:
            if self.state not in ('committed','uncertain'): self.state = 'aborted'

    def close(self): self.rollback()
    def __enter__(self): self._open(); return self
    def __exit__(self, *_): self.close()


def _json_document_payload(raw):
    value = json.loads(raw)
    if type(value) is not list or len(value) != 4 or any(type(v) is not str for v in value): raise BackendError('integrity')
    return value[0],value[1],_storage()._revision_number(value[2]),value[3]


def resolve(backend, operation, requests):
    _storage()._uuid(operation)
    if type(requests) is not tuple or not 1 <= len(requests) <= MAX_OPERATIONS: raise BackendError('invalid_input')
    view = backend.begin_read()
    try:
        from .sqlite_configuration_history import bind
        bind(view, 'unit', operation)
        if view._connection.execute("SELECT 1 FROM unit_of_work_receipt WHERE operation_id=? AND (typeof(request_hash)!='text' OR length(request_hash)!=64 OR typeof(outcomes_json)!='text' OR length(CAST(outcomes_json AS BLOB))>?)",(str(operation),MAX_BYTES)).fetchone(): raise BackendError('integrity')
        row = view._connection.execute('SELECT request_hash,outcomes_json FROM unit_of_work_receipt WHERE operation_id=?',(str(operation),)).fetchone()
        if row is None: return None
        bindings = json.loads(row[1]); expected_bindings = []; total = 0; identities = set()
        if type(bindings) is not list or len(bindings) != len(requests): raise BackendError('conflict')
        for index,request in enumerate(requests):
            digest,size,identity = _describe(view,request); total += size
            if (identity in identities and request.kind not in ('recorder_replace','accumulation_replace')) or total > MAX_BYTES: raise BackendError('invalid_input')
            identities.add(identity)
            entry = bindings[index]
            if type(entry) is not list or len(entry) != 5 or any(type(x) is not str for x in entry): raise BackendError('integrity')
            expected = [request.kind,str(_child(operation,index)),digest]
            if entry[:3] != expected: raise BackendError('conflict')
            child = entry[1]
            if request.kind=='document_set_posted':_require_staged_document(request.draft,requests[:index],bindings[:index])
            if request.kind.startswith('catalog_'):
                exists = view._connection.execute('SELECT 1 FROM commit_receipt WHERE operation_id=? AND request_hash=? AND revisions_json=?',(child,entry[3],entry[4])).fetchone()
            elif request.kind=='document_set_posted':
                exists=view._connection.execute('SELECT 1 FROM document_posting_receipt WHERE operation_id=? AND request_hash=? AND outcome_json=?',(child,entry[3],entry[4])).fetchone()
            elif request.kind.startswith('document_'):
                exists = view._connection.execute('SELECT 1 FROM document_commit_receipt WHERE operation_id=? AND request_hash=? AND document_id=? AND record_id=? AND revision=? AND number=?',(child,entry[3],*_json_document_payload(entry[4]))).fetchone()
            elif request.kind=='recorder_replace':
                _recorder_port(view)
                exists=view._connection.execute('SELECT 1 FROM recorder_movement_receipt WHERE operation_id=? AND request_hash=? AND outcome_json=?',(child,entry[3],entry[4])).fetchone()
            elif request.kind=='accumulation_replace':
                _accumulation_port(view)
                exists=view._connection.execute('SELECT 1 FROM accumulation_movement_receipt WHERE operation_id=? AND request_hash=? AND outcome_json=?',(child,entry[3],entry[4])).fetchone()
            else:
                exists = view._connection.execute('SELECT 1 FROM information_register_receipt WHERE operation_id=? AND request_hash=? AND outcome_json=?',(child,entry[3],entry[4])).fetchone()
            if not exists: raise BackendError('integrity')
            expected_bindings.append(expected)
        if total + len(row[1].encode('utf-8')) > MAX_BYTES: raise BackendError('unsupported')
        calculated = _hash(['unit_of_work_v1',str(view.database_id),view.configuration_generation,expected_bindings,row[1]])
        if calculated != row[0] or _json(bindings) != row[1]: raise BackendError('conflict')
    finally: view.close()
    # Legacy receipt resolvers already validate typed revisions, numbers and
    # frozen request hashes. Receipts are immutable and written atomically.
    results = []
    for index,request in enumerate(requests):
        child = _child(operation,index); kind,draft,expected = request.kind,request.draft,request.expected
        if kind.startswith('catalog_'):
            if backend.storage_version in (4,7,8,9,10): result = backend.resolve_write_outcome(child,draft,expected)
            else:
                revision = backend.resolve_write(child,draft,expected)
                schema = next((s for s in backend._schemas if s.identity==draft.key.catalog_id),None)
                if schema is None: raise BackendError('schema_changed')
                result = None if revision is None else CatalogWriteOutcome(revision,normalize_string(draft.code,schema.code_length))
        elif kind=='document_set_posted':
            from .sqlite_document_posting_state import resolve_posted_receipt
            borrowed=backend.begin_read()
            try:result=resolve_posted_receipt(borrowed._connection,borrowed.database_id,borrowed.configuration_generation,child,draft)
            finally:borrowed.close()
        elif kind.startswith('document_'): result = backend.resolve_document_write(child,draft,expected)
        elif kind=='recorder_replace':
            borrowed=backend.begin_read()
            try:result=_recorder_port(borrowed).resolve(child,draft)
            finally:borrowed.close()
        elif kind=='accumulation_replace':
            borrowed=backend.begin_read()
            try:result=_accumulation_port(borrowed).resolve(child,draft)
            finally:borrowed.close()
        elif kind == 'register_set': result = backend.resolve_register_set(child,draft)
        else: result = backend.resolve_register_write(child,draft,expected,kind == 'register_delete')
        if result is None: raise BackendError('integrity')
        results.append(TransactionOutcome(StagedTicket(operation,index,kind),result))
    return tuple(results)


for _method in ('stage','read_catalog','read_document','read_register','read_document_posted','read_recorder','read_accumulation','commit'):
    setattr(UnitOfWork,_method,_storage()._boundary(getattr(UnitOfWork,_method)))
