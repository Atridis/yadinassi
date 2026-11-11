"""Detached posting form images and receipt-only host recovery.

Neither a form interpreter nor the browser owns operation IDs or SQL journals.
The dedicated host consumes a full typed image only after dispatch is complete.
"""
from types import MappingProxyType
from uuid import uuid4
from secrets import token_hex
from .catalog_backend import BackendError
from .configuration_document import DocumentObjectSession, DocumentImage, DocumentSaveResult, require_document_form_schema
from .configuration_posting_application import canonical
from .document_posting_host import RootPostingOperations
from .documents import BSLDocumentObject
from .document_backend import DocumentSelection


class PostingDocumentSession:
    image = DocumentObjectSession.image
    _members = staticmethod(DocumentObjectSession._members)
    require_discardable = DocumentObjectSession.require_discardable

    def __init__(self, context, schema, configuration, form, key=None):
        require_document_form_schema(schema)
        self.context, self.schema = context, schema
        self.configuration = canonical(configuration)
        self._backend = context.backend
        self._sources = MappingProxyType(dict(configuration.files))
        self.form = form
        self.operations = RootPostingOperations(context, configuration)
        from .metadata import BSLMetadata
        from .catalogs import BSLCatalogs
        from .documents import BSLDocuments
        metadata = BSLMetadata(context)
        catalogs = BSLCatalogs(metadata._catalogs, context)
        self.manager = BSLDocuments(metadata._documents, context, catalogs).get_index(schema.name)
        self.fields = ('Number', 'Date', 'DeletionMark', 'Posted') + tuple(f.name for f in schema.fields)
        self._saving = False
        self.pending_commit = self.pending_refresh = False
        self.error = None; self.save_state = 'new'
        self._operation_id = None; self.receipt_token = None
        self.verify_source()
        if key is None:
            self.object = self.manager.create_document()
        else:
            view = self._backend.begin_document_read()
            try: card = view.read_document(key)
            finally: view.close()
            if card is None or key.document_id != schema.identity: raise BackendError('not_found')
            self.object = BSLDocumentObject(self.manager, card)
            self.save_state = 'unchanged'
        self.baseline = self.image(); self.listing = ()

    def verify_source(self):
        if self.context.backend is not self._backend:
            raise BackendError('schema_changed')
        self.operations.verify_source()

    def _candidate(self, image):
        if type(image) is not DocumentImage: raise TypeError('complete document image required')
        values = self._members(image.values, self.fields)
        if values['Posted'] is not self.object.get_member('Posted'):
            raise BackendError('conflict')
        # Reuse exact row identity and typed assignment checks without ever
        # invoking the ordinary session's persistence/admission path.
        fields = self.fields
        try:
            self.fields = tuple(name for name in fields if name != 'Posted')
            plain = DocumentImage(tuple(pair for pair in image.values if pair[0] != 'Posted'), image.sections)
            candidate = DocumentObjectSession._candidate(self, plain)
            candidate._values['posted'] = self.object.get_member('Posted')
            return candidate
        finally: self.fields = fields

    def _refresh(self, validate_result):
        self.verify_source()
        view = self._backend.begin_document_read()
        try:
            card = view.read_document(self.object._key)
            if card is None: raise BackendError('not_found')
            listing = view.select_documents(self.schema.identity, DocumentSelection())
            if not any(row.key == card.key for row in listing): raise BackendError('not_found')
        finally: view.close()
        fresh = BSLDocumentObject(self.manager, card)
        image = self.image(fresh)
        result = DocumentSaveResult('saved', None, image, card.key, listing)
        if validate_result is not None: validate_result(result)
        self.object, self.baseline, self.listing = fresh, image, listing
        self.pending_commit = self.pending_refresh = False
        self.save_state, self.error = 'saved', None
        return result

    def _try_refresh(self, validate_result):
        try: return self._refresh(validate_result)
        except Exception:
            self.pending_refresh = True
            self.save_state, self.error = 'committed', 'refresh_required'
            return DocumentSaveResult(self.save_state, self.error)

    def _accept_receipt(self, receipt, validate_result):
        if receipt.state == 'committed':
            self.pending_commit = not receipt.accepted
            self.pending_refresh = True
            self.save_state, self.error = 'committed', 'refresh_required'
            if receipt.accepted: return self._try_refresh(validate_result)
        elif receipt.state in ('uncertain', 'prepared'):
            self.pending_commit = True
            self.save_state, self.error = 'uncertain', 'outcome_unknown'
        else:
            self.pending_commit = self.pending_refresh = False
            self.save_state, self.error = 'rejected', 'operation_refused'
        return DocumentSaveResult(self.save_state, self.error)

    def execute(self, command, image, *, validate_result=None):
        if self._saving: raise BackendError('busy')
        if self.pending_commit or self.pending_refresh: raise BackendError('uncertain_commit')
        self.verify_source()
        candidate = self._candidate(image)
        operation_id, receipt_token = uuid4(), token_hex(16)
        self._saving = True
        # Bind before the first effect. The browser receives only this opaque,
        # form-local receipt capability, never the UUID or expected revision.
        self._operation_id, self.receipt_token = operation_id, receipt_token
        self.pending_commit = True
        self.object = candidate
        try:
            receipt = self.operations.execute(self._operation_id, candidate._draft(), candidate._revision,
                form=self.form, command=command)
            return self._accept_receipt(receipt, validate_result)
        except Exception:
            try: receipt = self.operations.receipt(self._operation_id)
            except BackendError:
                self.pending_commit = False
                self.save_state, self.error = 'rejected', 'operation_refused'
                return DocumentSaveResult(self.save_state, self.error)
            return self._accept_receipt(receipt, validate_result)
        finally: self._saving = False

    def recover(self, receipt_token, *, validate_result=None):
        if receipt_token != self.receipt_token or self._operation_id is None:
            raise BackendError('conflict')
        if self._saving: raise BackendError('busy')
        self._saving = True
        try:
            if self.pending_commit:
                return self._accept_receipt(self.operations.resolve(self._operation_id), validate_result)
            if self.pending_refresh: return self._try_refresh(validate_result)
            return DocumentSaveResult(self.save_state, self.error)
        except Exception:
            return DocumentSaveResult(self.save_state, self.error)
        finally: self._saving = False

    def save(self, *args, **kwargs):
        raise BackendError('unsupported')

    def close(self):
        self.require_discardable()
        self.operations.close()


def dispatch_posting(definition, server, owned, action, command=None, receipt=None):
    """Called by the trusted broker after server dispatch has fully returned."""
    from .form_replication import _pack_state
    from .form_tables import BSLFormDataCollection
    from .ui.protocol import encode_line
    session = server.session
    if session.state != 'open' or session._busy:
        raise ValueError('posting requires a completed open-form dispatch')
    def preflight(result):
        if hasattr(owned, 'projection_preflight'): owned.projection_preflight(result.listing)
        if len(result.listing) > 256: raise ValueError('posting list projection limit')
        previous_data, previous_tables, previous_ids = session.form._data, session.form._tables, session._document_row_ids
        try:
            session.form._data = previous_data.copy()
            session.form._tables = {schema.name.casefold(): BSLFormDataCollection(session.form, schema, i)
                for i, schema in enumerate((table.schema for table in previous_tables.values()), 1)}
            for key, table in session.form._tables.items():
                old = previous_tables[key]._snapshot(); table._replace_rows(old.rows, old.allocated)
            definition._install_document_image(session, result.image)
            encode_line(_pack_state(session, session._replica_handler_names))
        finally:
            session.form._data, session.form._tables, session._document_row_ids = previous_data, previous_tables, previous_ids
    if action == 'execute':
        result = owned.execute(command, definition._document_image(session), validate_result=preflight)
    elif action == 'recover':
        result = owned.recover(receipt, validate_result=preflight)
    elif action == 'sync':
        result = None
    else: raise ValueError('unknown posting action')
    if result is not None and result.image is not None:
        definition._install_document_image(session, result.image)
    locked = owned.pending_commit or owned.pending_refresh
    if locked and not hasattr(owned, '_locked_controls'):
        owned._locked_controls = {key: (item.visible, item.enabled, item.read_only)
            for key, item in session.form.items._values.items()}
        posted_slot = dict(definition.object_fields)['Posted']
        for item in session.form.items._values.values():
            item.enabled = False
            item.read_only = True
            if item.data_path == posted_slot: item.visible = False
    elif not locked and hasattr(owned, '_locked_controls'):
        for key, flags in owned._locked_controls.items():
            item = session.form.items._values[key]
            item.visible, item.enabled, item.read_only = flags
        del owned._locked_controls
    return {'receipt': owned.receipt_token, 'state': owned.save_state,
            'error': owned.error, 'posted': None if locked else owned.object.get_member('Posted')}


def recover_posting_frame(definition, server, owned, frame, receipt):
    """Receipt-only trusted barrier. Never invokes a form/BSL routine.

    A retained SQL cleanup owner can prohibit all interpreter transfers. Recovery
    therefore validates the existing replica envelope but admits no draft delta.
    """
    from .form_replication import PROTOCOL, MAX_CALLS
    from .ui.protocol import decode_line
    if receipt != owned.receipt_token or owned._operation_id is None:
        raise ValueError('wrong posting receipt capability')
    if not server._gate.acquire(blocking=False): raise ValueError('posting recovery busy')
    try:
        binding = next(b for b in server.bindings if b.name == 'YadinassiPostingSync')
        if (set(frame) != set('protocol id operation revision sequence endpoint arguments delta'.split())
                or frame['protocol'] != PROTOCOL or frame['operation'] != 'call'
                or type(frame['id']) is not int or frame['id'] <= server._last_id
                or type(frame['revision']) is not int or frame['revision'] != server.session.revision
                or type(frame['sequence']) is not int or frame['sequence'] != server._sequence + 1
                or frame['endpoint'] != binding.endpoint or frame['arguments'] != []
                or frame['delta'] != {'attributes': [], 'items': [], 'title': None, 'cells': [], 'selections': []}
                or server._requests >= MAX_CALLS or server.session._busy or server.session.state != 'open'):
            raise ValueError('invalid receipt recovery barrier')
        state = dispatch_posting(definition, server, owned, 'recover', receipt=receipt)
        server._last_id = frame['id']; server._requests += 1; server._sequence += 1
        server.session.revision += 1
        return {'form': decode_line(server._reply(frame['id'], accepted=True)), 'posting': state}
    finally:
        server._gate.release()
