"""Host-owned ordered multi-port staging with one durable commit boundary."""
from contextlib import contextmanager
from yadinassi.db.catalog.catalog_backend import BackendError, Revision
from yadinassi.db.document.document_backend import DocumentRevision, DocumentWriteOutcome
from yadinassi.db.transaction_backend import TransactionRequest, StagedTicket, TransactionOutcome
from .sqlite_documents import DocumentView
from .sqlite_registers import RegisterView

MAX_OPERATIONS = 256
MAX_BYTES = 16 * 1024 * 1024
KINDS = ('catalog_create','catalog_update','document_create','document_update',
         'register_write','register_delete','register_set','recorder_replace','accumulation_replace','document_set_posted')


def _storage():
    from . import sqlite_catalog
    return sqlite_catalog


def _json(value): return _storage()._json(value)


def _require_movement_scan(connection, query_view):
    if query_view is not None and type(query_view) is _storage()._View:
        query_view._require()
        if (query_view._query_language and query_view._operation_id is None
                and query_view._backend._active is query_view
                and query_view._connection is connection
                and query_view._read_handle is query_view._backend._read_handle
                and query_view._read_handle is not None
                and query_view._read_handle.connection is connection):
            return
    if not connection.in_transaction:
        raise BackendError('closed')


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
        draft,values,schema = view._draft(draft); sections = view._draft_sections(draft,schema)
        if expected is not None and (type(expected) is not Revision or (expected.database_id,expected.configuration_generation,expected.catalog_id,expected.record_id)!=(view.database_id,view.configuration_generation,draft.key.catalog_id,draft.key.record_id)): raise BackendError('conflict')
        revision = 1 if expected is None else _storage()._revision_number(expected.token)+1
        intent = _storage()._intent(draft,revision,values,sections,
                     hierarchy=schema.hierarchy != 'none')
        identity = ('catalog',draft.key.catalog_id,draft.key.record_id)
        return len(_json(intent).encode('utf-8')), identity
    if kind.startswith('document_'):
        port = DocumentView(view)
        _,intent,_ = port._intent(draft,expected)
        return len(_json(intent).encode('utf-8')),('document',draft.key.document_id,draft.key.record_id)
    port = RegisterView(view)
    if kind == 'register_set':
        if expected is not None: raise BackendError('invalid_input')
        schema,rows,_ = port._set_intent(draft)
        _,wanted = port._filter_values(schema,draft.filters)
        intent = ['register_set_v1',str(schema.identity),[[str(f.identity),wanted[f.identity]] for f in schema.key_fields if f.identity in wanted],rows,draft.replace,draft.expected_snapshot]
        size = len(_json(intent).encode('utf-8'))
    else:
        schema,raw,values,_ = port._intent(draft,expected,kind == 'register_delete')
        intent = ['register_write_v1',str(schema.identity),raw,values,None if expected is None else expected.token,kind == 'register_delete']
        size = len(_json(intent).encode('utf-8'))
    # One mutation per register prevents overlapping set/single-key intents.
    return size,('register',schema.identity)


def _require_staged_document(intent,view,requests,results):
    # A posting state transition requires this same unit's actual document CAS.
    for request,outcome in zip(requests,results):
        if request.kind not in ('document_create','document_update') or request.draft.key!=intent.recorder:
            continue
        result = outcome.result
        if type(result) is not DocumentWriteOutcome or type(result.revision) is not DocumentRevision:
            raise BackendError('integrity')
        revision = result.revision
        key = intent.recorder
        if (revision.database_id,revision.configuration_generation,revision.document_id,revision.record_id,
                revision.token)==(key.database_id,view.configuration_generation,key.document_id,key.record_id,
                                   str(intent.document_revision)):
            return
    raise BackendError('conflict')


class UnitOfWork:
    """Explicit commit only. A ticket proves staging, not persistent success."""
    def __init__(self, view):
        self._view = view; self.operation_id = view._operation_id
        self._requests = (); self._results = (); self._identities = frozenset()
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
        size,identity = _describe(view,request)
        if identity in self._identities and request.kind not in ('recorder_replace','accumulation_replace'): raise BackendError('unsupported')
        total = self._bytes + size
        if total > MAX_BYTES: raise BackendError('unsupported')
        index = len(self._requests)
        kind,draft,expected = request.kind,request.draft,request.expected
        if kind=='document_set_posted':_require_staged_document(draft,view,self._requests,self._results)
        # Commit row changes and stage bookkeeping together under the savepoint.
        with view._atomic_record():
            if kind.startswith('catalog_'):
                if expected is None: view.create(draft)
                else: view.update(draft,expected)
                result = view._outcomes[-1]
            elif kind=='document_set_posted':
                from .sqlite_document_posting_state import stage_posted
                result = stage_posted(view._connection,view.database_id,draft)
            elif kind.startswith('document_'):
                port = DocumentView(view)
                if expected is None: port.create(draft)
                else: port.update(draft,expected)
                result = port._outcome
            elif kind=='recorder_replace':
                result = _recorder_port(view).replace(draft)
            elif kind=='accumulation_replace':
                result = _accumulation_port(view).replace(draft)
            else:
                port = RegisterView(view)
                if kind == 'register_set': port.write_set(draft)
                elif kind == 'register_delete': port.delete(draft,expected)
                else: port.write(draft,expected)
                result = port._outcome
            ticket = StagedTicket(self.operation_id,index,kind)
            requests = (*self._requests,request)
            results = (*self._results,TransactionOutcome(ticket,result))
            identities = self._identities | {identity}
        self._requests,self._results,self._identities,self._bytes = requests,results,identities,total
        return ticket

    @contextmanager
    def savepoint(self):
        """Rollback one host operation and journal; keep earlier root stages."""
        self._open()
        if self._savepoint_depth>=32:raise BackendError('unsupported')
        before=(self._requests,self._results,self._identities,self._bytes)
        self._savepoint_depth+=1
        try:
            with self._view._atomic_record():yield self
        except BaseException:
            self._requests,self._results,self._identities,self._bytes=before
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
        self.state = 'committing'
        try:
            self._view._connection.execute('COMMIT')
            self.state = 'committed'
            self._view.close()
        except BaseException as error:
            # A returned COMMIT is certain even if closing the connection fails.
            # A lost COMMIT response is terminal; do not infer rollback or replay.
            if self.state != 'committed':
                self.state = 'uncertain'
            try: self._view.close()
            except BaseException as cleanup:
                if _storage()._interruption(cleanup) and not _storage()._interruption(error): raise
            if self.state == 'committed' or _storage()._interruption(error): raise
            raise BackendError('uncertain_commit') from None
        return self._results

    def rollback(self):
        try: self._view.close()
        finally:
            if self.state not in ('committed','uncertain'): self.state = 'aborted'

    def close(self): self.rollback()
    def __enter__(self): self._open(); return self
    def __exit__(self, *_): self.close()


def acknowledge_root(root):
    raise BackendError('unsupported')


def resolve(backend, operation, requests):
    # Returning None would tell a legacy caller it may retry the write.
    raise BackendError('unsupported')


for _method in ('stage','read_catalog','read_document','read_register','read_document_posted','read_recorder','read_accumulation','commit'):
    setattr(UnitOfWork,_method,_storage()._boundary(getattr(UnitOfWork,_method)))
