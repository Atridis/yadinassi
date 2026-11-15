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


ACK_SCHEMA = 'unit-of-work-ack-v2'


def _child_payload(view, entry):
    """Rehydrate only a canonical bounded child with the exact retained hash."""
    kind, child, intent_hash, receipt_hash = entry
    if kind not in KINDS: raise BackendError('integrity')
    if kind.startswith('catalog_'):
        table, column = 'commit_receipt', 'revisions_json'
    elif kind.startswith('document_') and kind != 'document_set_posted':
        shape = view._connection.execute("SELECT typeof(document_id),length(CAST(document_id AS BLOB)),typeof(record_id),length(CAST(record_id AS BLOB)),typeof(revision),CASE WHEN typeof(revision)='integer' THEN revision ELSE NULL END,typeof(number),length(CAST(number AS BLOB)) FROM document_commit_receipt WHERE operation_id=? AND request_hash=?", (child,receipt_hash)).fetchone()
        if (shape is None or shape[0:4] != ('text',36,'text',36)
                or shape[4] != 'integer' or not 1 <= shape[5] < 2**63-1
                or shape[6] != 'text' or not 0 <= shape[7] <= 65536):
            raise BackendError('integrity')
        row = view._connection.execute('SELECT document_id,record_id,revision,number FROM document_commit_receipt WHERE operation_id=?',(child,)).fetchone()
        return _json([row[0],row[1],str(row[2]),row[3]])
    else:
        table = {'document_set_posted':'document_posting_receipt',
                 'recorder_replace':'recorder_movement_receipt',
                 'accumulation_replace':'accumulation_movement_receipt'}.get(kind,'information_register_receipt')
        column = 'outcome_json'
    shape = view._connection.execute('SELECT typeof('+column+'),length(CAST('+column+' AS BLOB)) FROM '+table+' WHERE operation_id=? AND request_hash=?',(child,receipt_hash)).fetchone()
    if shape is None or shape[0] != 'text' or not 0 <= shape[1] <= MAX_BYTES:
        raise BackendError('integrity')
    return view._connection.execute('SELECT '+column+' FROM '+table+' WHERE operation_id=?',(child,)).fetchone()[0]


def _quoted_json_size(value, limit):
    """Size of ensure_ascii JSON string without allocating its escaped copy."""
    size = 2
    if size > limit: raise BackendError('unsupported')
    for char in value:
        code = ord(char)
        size += (2 if char in '\\"\b\f\n\r\t' else
                 1 if 32 <= code < 127 else 6 if code <= 65535 else 12)
        if size > limit: raise BackendError('unsupported')
    return size


def _receipt_bindings(view, raw):
    value = json.loads(raw)
    if type(value) is not dict or value.get('schema') != ACK_SCHEMA: return value
    if (type(value) is not dict or set(value) != {'schema','bindings'}
            or value['schema'] != ACK_SCHEMA or _json({'schema':ACK_SCHEMA,'bindings':value['bindings']}) != raw
            or view._backend.format_version not in (13,15,16)):
        raise BackendError('integrity')
    entries = value['bindings']
    if type(entries) is not list or not 1 <= len(entries) <= MAX_OPERATIONS:
        raise BackendError('integrity')
    result = []; size = 2
    for entry in entries:
        if type(entry) is not list or len(entry) != 4 or any(type(x) is not str for x in entry):
            raise BackendError('integrity')
        if (str(UUID(entry[1])) != entry[1] or not UUID(entry[1]).int
                or any(len(v) != 64 or any(c not in '0123456789abcdef' for c in v) for v in entry[2:])):
            raise BackendError('integrity')
        payload = _child_payload(view,entry)
        size += (1 if result else 0) + len(_json(entry)) + 1
        size += _quoted_json_size(payload,MAX_BYTES-size)
        if size > MAX_BYTES: raise BackendError('unsupported')
        result.append([*entry,payload])
    return result


def _commit_acknowledgement(connection):
    connection.execute('COMMIT')


def acknowledge_root(root):
    """Explicit accepted-host-root payload compaction; retain every child/UUID.

    No epoch-bound v12 receipts, no automatic deletion, no retention horizon.
    The old root digest remains a commitment to the rehydrated v1 outcome bytes.
    """
    from uuid import uuid4
    from .transaction_backend import TransactionAcknowledgement
    root._admit_root(root.backend)
    if (root.backend.format_version not in (13,15,16) or root._images is None
            or root.receipt is not root._images[2] or not root.receipt.accepted
            or root.locked or root._transaction is None):
        raise BackendError('unsupported')
    receipt = root.receipt
    if root.backend.resolve_unit_of_work(receipt.operation_id,receipt.requests) != receipt.outcomes:
        raise BackendError('integrity')
    view = root.backend.begin_write(uuid4())
    try:
        shape = view._connection.execute('SELECT typeof(request_hash),length(CAST(request_hash AS BLOB)),typeof(outcomes_json),length(CAST(outcomes_json AS BLOB)) FROM unit_of_work_receipt WHERE operation_id=?',(str(receipt.operation_id),)).fetchone()
        if (shape is None or shape[:3] != ('text',64,'text') or not 0 <= shape[3] <= MAX_BYTES):
            raise BackendError('integrity')
        row = view._connection.execute('SELECT request_hash,outcomes_json FROM unit_of_work_receipt WHERE operation_id=?',(str(receipt.operation_id),)).fetchone()
        if (row is None or type(row[1]) is not str or len(row[1].encode('utf-8')) > MAX_BYTES):
            raise BackendError('integrity')
        bindings = _receipt_bindings(view,row[1])
        encoded = _json(bindings)
        expected = _json(root._transaction.unit._bindings)
        digest = _hash(['unit_of_work_v1',str(view.database_id),view.configuration_generation,
                        [entry[:3] for entry in bindings],encoded])
        if encoded != expected or digest != row[0]: raise BackendError('integrity')
        # Compare child bytes again under the writer lock; the preceding typed
        # resolution is not a reusable integrity fact across separate snapshots.
        for entry in bindings:
            if _child_payload(view,entry[:4]) != entry[4]: raise BackendError('integrity')
        compact = _json({'schema':ACK_SCHEMA,'bindings':[entry[:4] for entry in bindings]})
        result = TransactionAcknowledgement(receipt.operation_id,2,len(bindings),
                    len(encoded.encode('utf-8')),len(compact.encode('utf-8')))
        if row[1] == compact: return result
        if row[1] != encoded: raise BackendError('integrity')
        cursor = view._connection.execute('UPDATE unit_of_work_receipt SET outcomes_json=? WHERE operation_id=? AND request_hash=? AND outcomes_json=?',
                            (compact,str(receipt.operation_id),row[0],row[1]))
        if cursor.rowcount != 1: raise BackendError('conflict')
        try:
            _commit_acknowledgement(view._connection)
            view.close()
        except BaseException as error:
            if _storage()._interruption(error): raise
            raise BackendError('uncertain_commit') from None
        return result
    finally: view.close()


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
        bindings = _receipt_bindings(view,row[1]); encoded = _json(bindings)
        expected_bindings = []; total = 0; identities = set()
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
        if total + len(encoded.encode('utf-8')) > MAX_BYTES: raise BackendError('unsupported')
        calculated = _hash(['unit_of_work_v1',str(view.database_id),view.configuration_generation,expected_bindings,encoded])
        if calculated != row[0] or (type(json.loads(row[1])) is list and encoded != row[1]): raise BackendError('conflict')
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

acknowledge_root = _storage()._boundary(acknowledge_root)
