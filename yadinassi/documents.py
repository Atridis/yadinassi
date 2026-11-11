"""Detached BSL document lifecycle over a logical document port.

This is a bounded local application contract, not unmeasured native parity.
"""
from decimal import Decimal
from uuid import UUID, uuid4

from .catalog_backend import BackendError, TabularSectionRows
from .catalogs import BSLCatalogManager
from .catalog_qualifiers import normalize_string, validate_string
from .catalog_sections import _MAX_ROWS, _MAX_BUFFER_BYTES
from .dates import BSLDate, _date_from_datetime, _parts, TICKS_PER_SECOND
from .document_backend import DocumentKey, DocumentDraft, DocumentSelection, DocumentWriteOutcome, DocumentRevision
from .document_types import BSLDocumentReference, BSLDocumentType
from .document_lines import BSLDocumentLines, BSLDocumentSectionType
from .unique_identifiers import BSLUUID
from .values import BSLObject, HostFunction

_ZERO = UUID(int=0)
_OMITTED = object()
_ALIASES = {'номер':'number','дата':'date','проведен':'posted','проведён':'posted',
            'ссылка':'ref','пометкаудаления':'deletionmark'}


def _name(name):
    if type(name) is not str: raise TypeError('document field requires String')
    return _ALIASES.get(name.casefold(),name.casefold())


def _field(values,name):
    key = _name(name)
    if key not in values: raise ValueError('document field not found')
    return values[key]


def _date(value):
    if type(value) is not BSLDate: raise TypeError('Date required')
    value.require_known()
    if value.ticks % TICKS_PER_SECOND: raise ValueError('subsecond document date unsupported')
    return _parts(value)


class BSLDocuments(BSLObject):
    def __init__(self, metadata, context, catalogs):
        self._metadata,self._context,self._catalogs = metadata,context,catalogs
        self._managers = {}
        self._interpreter = None
        self._posting_runtime = None
    def get_member(self,name): return self.get_index(name)
    def get_index(self,name):
        if type(name) is not str: raise TypeError('document name requires String')
        item = self._metadata._snapshot().get(name.casefold())
        if item is None: raise ValueError('document name not found')
        key = item._name.casefold()
        if key not in self._managers: self._managers[key] = BSLDocumentManager(self,item)
        return self._managers[key]
    def posting_runtime(self):
        if self._context is None: return None
        from .configuration_posting import PostingConfiguration
        backend = self._context.backend
        from .sqlite_catalog import SQLiteCatalogBackend
        if type(backend) is not SQLiteCatalogBackend: return None
        configuration = backend.posting_configuration
        if type(configuration) is not PostingConfiguration: return None
        if self._posting_runtime is None:
            from .document_posting import PostingRuntime
            self._posting_runtime = PostingRuntime(self, configuration)
        return self._posting_runtime
    def type_by_name(self,name):
        if type(name) is str:
            prefix,separator,tail = name.partition('.')
            families = {'documentref':'_value_type','документссылка':'_value_type',
                'documentmanager':'_manager_type','документменеджер':'_manager_type',
                'documentselection':'_selection_type','документвыборка':'_selection_type',
                'documentobject':'_object_type','документобъект':'_object_type'}
            if separator and prefix.casefold() in families: return getattr(self.get_index(tail),families[prefix.casefold()])
            sections = {'documenttabularsection':'section','документтабличнаячасть':'section',
                        'documenttabularsectionrow':'row','документтабличнаячастьстрока':'row'}
            if separator and prefix.casefold() in sections:
                document,_,section = tail.partition('.')
                manager = self.get_index(document)
                schema = next((s for s in manager._schema.tabular_sections if s.name.casefold() == section.casefold()),None)
                if schema is None: raise ValueError('document section not found')
                return manager._section_type(schema,sections[prefix.casefold()])
        return self._catalogs.type_by_name(name)
    def __str__(self): return 'Документы менеджер'


class BSLDocumentManager(BSLObject):
    # Identical bounded scalar conversion/qualification shared with catalogs.
    _logical = BSLCatalogManager._logical
    _stored = BSLCatalogManager._stored
    _field_default = BSLCatalogManager._field_default
    _assigned = BSLCatalogManager._assigned

    def __init__(self,documents,metadata):
        self._documents,self._metadata = documents,metadata
        self._catalogs = documents._catalogs
        self._schema = metadata._schema
        # Initialize catalog metadata in the same runtime snapshot for reference fields.
        self._catalogs._metadata._snapshot()
        for attr,family in (('_value_type','ref'),('_manager_type','manager'),('_selection_type','selection'),('_object_type','object')):
            setattr(self,attr,BSLDocumentType(self._schema.identity,self._schema.name,documents._metadata,family))
    @property
    def _backend(self): return self._documents._context.backend
    def _writable(self):
        caps = self._backend.capabilities()
        return caps.atomic_transactions and caps.document_create and caps.document_update
    def _view(self):
        from .database_transactions import forbid_transfer
        forbid_transfer(self._backend)
        view = self._backend.begin_document_read()
        try: self._check_view(view)
        except BaseException as error:
            try: view.close()
            except BaseException as cleanup:
                if (not isinstance(cleanup,Exception) or isinstance(cleanup,MemoryError)) and isinstance(error,Exception) and not isinstance(error,MemoryError): raise
            raise
        return view
    def _check_view(self,view):
        m = self._documents._metadata
        if (view.database_id,view.configuration_generation,view.document_schema(self._schema.identity)) != (m._database_id,m._generation,self._schema): raise BackendError('schema_changed')
    def _key(self,record): return DocumentKey(self._documents._metadata._database_id,self._schema.identity,record)
    def _ref(self,record): return BSLDocumentReference(self._value_type,record,self._metadata,self._read_member,self._get_object)
    def _section_type(self,schema,family): return BSLDocumentSectionType(self._schema.identity,schema.identity,schema.name,self._documents._metadata,family)
    def empty_ref(self): return self._ref(_ZERO)
    def get_ref(self,uuid=_OMITTED):
        if uuid is _OMITTED or uuid is None: uuid = BSLUUID()
        if type(uuid) is not BSLUUID: raise TypeError('GetRef requires UUID')
        return self._ref(UUID(uuid.text))
    def _defaults(self,ref=None):
        values = {'number':'','date':BSLDate(0),'deletionmark':False,'posted':False,'ref':ref}
        values.update((f.name.casefold(),self._field_default(f)) for f in self._schema.fields)
        return values
    def _fields(self,card):
        if (card.key.database_id,card.key.document_id,len(card.values)) != (self._key(_ZERO).database_id,self._schema.identity,len(self._schema.fields)): raise BackendError('integrity')
        posted = getattr(card,'posted',False)
        if type(posted) is not bool: raise BackendError('integrity')
        values = {'number':card.number,'date':_date_from_datetime(card.date),'deletionmark':card.deletion_mark,'posted':posted,'ref':self._ref(card.key.record_id)}
        values.update((f.name.casefold(),self._logical(f,v)) for f,v in zip(self._schema.fields,card.values))
        return values
    def _read(self,record):
        view = self._view()
        try: return view.read_document(self._key(record))
        finally: view.close()
    def _read_member(self,ref,name):
        card = self._read(ref.reference_uuid)
        return _field(self._defaults(ref) if card is None else self._fields(card),name)
    def _get_object(self,ref):
        card = self._read(ref.reference_uuid)
        return None if card is None else BSLDocumentObject(self,card)
    def create_document(self):
        if not self._writable(): raise BackendError('unsupported')
        return BSLDocumentObject(self)
    def find_by_number(self,number):
        if type(number) is not str: raise TypeError('Number requires String')
        view = self._view()
        try: key = view.find_document_number(self._schema.identity,number)
        finally: view.close()
        return self.empty_ref() if key is None else self._ref(key.record_id)
    def select(self,start=None,end=None):
        request = DocumentSelection(None if start is None else _date(start),None if end is None else _date(end))
        view = self._view()
        try: rows = view.select_documents(self._schema.identity,request)
        finally: view.close()
        return BSLDocumentSelection(self,rows)
    def get_member(self,name):
        methods = {'emptyref':self.empty_ref,'пустаяссылка':self.empty_ref,'getref':self.get_ref,'получитьссылку':self.get_ref,
                   'createdocument':self.create_document,'создатьдокумент':self.create_document,
                   'findbynumber':self.find_by_number,'найтипономеру':self.find_by_number,'select':self.select,'выбрать':self.select}
        method = methods.get(name.casefold())
        return HostFunction(name,method) if method else super().get_member(name)
    def __str__(self): return str(self._manager_type)


class BSLDocumentObject(BSLObject):
    def __init__(self,manager,card=None):
        self._manager = manager; self._object_type = manager._object_type
        self._key = manager._key(uuid4()) if card is None else card.key
        self._revision = None if card is None else card.revision
        self._values = manager._defaults(manager.empty_ref()) if card is None else manager._fields(card)
        self._operation_id = uuid4(); self._pending_write = None
        self._posting_previous = None; self._posting_active = None
        from .structures import BSLStructure
        self._additional_properties = BSLStructure()
        self._movements = None
        contents = {} if card is None else {s.section_id:s for s in card.tabular_sections}
        if card is not None and (len(contents) != len(card.tabular_sections) or set(contents) != {s.identity for s in manager._schema.tabular_sections}): raise BackendError('integrity')
        self._sections = {s.name.casefold():BSLDocumentLines(self,s,() if card is None else contents[s.identity].rows) for s in manager._schema.tabular_sections}
        if self._section_row_count() > _MAX_ROWS or self._section_buffer_bytes() > _MAX_BUFFER_BYTES: raise BackendError('unsupported')
    def _section_row_count(self): return sum(len(s._rows) for s in self._sections.values())
    def _section_buffer_bytes(self): return sum(s._bytes for s in self._sections.values())
    def is_new(self): return self._revision is None
    def set_new_object_ref(self,ref):
        if self._pending_write is not None: raise BackendError('uncertain_commit')
        if not self.is_new(): raise ValueError('document already persisted')
        if type(ref) is not BSLDocumentReference or ref.value_type != self._manager._value_type or ref.is_empty(): raise TypeError('same-document nonempty reference required')
        self._key = self._manager._key(ref.reference_uuid)
    def _accept(self,outcome):
        if type(outcome) is not DocumentWriteOutcome or type(outcome.revision) is not DocumentRevision: raise BackendError('uncertain_commit')
        r = outcome.revision; m = self._manager
        if (r.database_id,r.configuration_generation,r.document_id,r.record_id) != (self._key.database_id,m._documents._metadata._generation,self._key.document_id,self._key.record_id): raise BackendError('uncertain_commit')
        validate_string(outcome.number,m._schema.number_length)
        draft,expected,_ = self._pending_write
        if r.token != ('1' if expected is None else str(int(expected.token)+1)): raise BackendError('uncertain_commit')
        if draft.auto_number:
            if len(outcome.number) != m._schema.number_length or not outcome.number.isascii() or not outcome.number.isdecimal() or int(outcome.number) == 0: raise BackendError('uncertain_commit')
        elif outcome.number != draft.number: raise BackendError('uncertain_commit')
        values = dict(self._values)
        values['number'] = outcome.number; values['ref'] = m._ref(self._key.record_id)
        next_operation = uuid4()
        self._revision = r; self._values = values; self._operation_id = next_operation
        for section in self._sections.values(): section._dirty = False
        self._pending_write = None
        self._posting_previous = None
    def _draft(self):
        m = self._manager
        return DocumentDraft(self._key,self._values['number'],_date(self._values['date']),self._values['deletionmark'],
            tuple(m._stored(f,self._values[f.name.casefold()]) for f in m._schema.fields),
            tuple(s._stored_rows() for s in self._sections.values()),
            self.is_new() and m._schema.numbering == 'decimal_v1' and self._values['number'] == '')
    def _rollback_pending(self):
        if self._posting_previous is not None:
            self._values['posted'] = self._posting_previous
        self._posting_previous = None
        self._pending_write = None
    def write(self, mode=_OMITTED):
        posting = self._manager._documents.posting_runtime()
        if posting is not None: return posting.write(self, mode)
        if mode is not _OMITTED: raise BackendError('unsupported')
        m = self._manager
        from .database_transactions import current
        transaction = current(m._backend)
        if transaction is not None and self._pending_write is not None: raise BackendError('unsupported')
        if not m._writable(): raise BackendError('unsupported')
        if self._pending_write is not None:
            draft,expected,operation = self._pending_write
            result = m._backend.resolve_document_write(operation,draft,expected)
            if result is not None: self._accept(result); return None
        else:
            sections = tuple(s._stored_rows() for s in self._sections.values())
            draft = DocumentDraft(self._key,self._values['number'],_date(self._values['date']),self._values['deletionmark'],
                tuple(m._stored(f,self._values[f.name.casefold()]) for f in m._schema.fields),sections,
                self.is_new() and m._schema.numbering == 'decimal_v1' and self._values['number'] == '')
            expected,operation = self._revision,self._operation_id
        if transaction is not None:
            transaction.stage(self, 'document_create' if expected is None else 'document_update',
                              draft, expected, (draft,expected,operation))
            return None
        tx = m._backend.begin_document_write(operation); committing = False
        try:
            m._check_view(tx)
            if expected is None: tx.create(draft)
            else: tx.update(draft,expected)
            self._pending_write = (draft,expected,operation); committing = True
            result = tx.commit(); tx.close(); self._accept(result)
        except BaseException as error:
            if not committing: self._pending_write = None
            for cleanup in (tx.rollback,tx.close):
                try: cleanup()
                except BaseException as cleanup_error:
                    if (not isinstance(cleanup_error,Exception) or isinstance(cleanup_error,MemoryError)) and isinstance(error,Exception) and not isinstance(error,MemoryError): error = cleanup_error
            if committing and isinstance(error,Exception) and not isinstance(error,MemoryError): raise BackendError('uncertain_commit') from None
            raise error
        return None
    def get_member(self,name):
        key = _name(name)
        methods = {'write':self.write,'записать':self.write,'isnew':self.is_new,'этоновый':self.is_new,
                   'setnewobjectref':self.set_new_object_ref,'установитьссылкунового':self.set_new_object_ref,
                   'metadata':lambda:self._manager._metadata,'метаданные':lambda:self._manager._metadata}
        if key in methods: return HostFunction(name,methods[key])
        if key in self._sections: return self._sections[key]
        posting = self._manager._documents.posting_runtime()
        if posting is not None:
            if key in ('additionalproperties','дополнительныесвойства'): return self._additional_properties
            if key in ('registerrecords','движения'): return posting.movements(self)
        return _field(self._values,name)
    def set_member(self,name,value):
        if self._pending_write is not None: raise BackendError('uncertain_commit')
        key = _name(name)
        if key in ('ref','posted') or key in self._sections: raise ValueError('document property is read-only')
        if key not in self._values: raise ValueError('document field not found')
        if key == 'number': value = normalize_string(value,self._manager._schema.number_length)
        elif key == 'date': _date(value)
        elif key == 'deletionmark':
            if type(value) is not bool: raise TypeError('DeletionMark requires Boolean')
        else:
            field = next(f for f in self._manager._schema.fields if f.name.casefold() == key)
            value = self._manager._assigned(field,value)
        self._values[key] = value
    def __str__(self): raise ValueError('document object presentation is unsupported')


class BSLDocumentSelection(BSLObject):
    def __init__(self,manager,rows):
        self._manager = manager; self._selection_type = manager._selection_type
        self._rows = tuple(rows); self._position = -1
    def next(self):
        if self._position < len(self._rows): self._position += 1
        return self._position < len(self._rows)
    def get_method(self,name):
        if name.casefold() in ('next','следующий'): return HostFunction(name,self.next)
        if name.casefold() in ('getobject','получитьобъект'):
            return HostFunction(name,lambda:BSLDocumentObject(self._manager,self._rows[self._position]) if 0 <= self._position < len(self._rows) else None)
        return super().get_method(name)
    def get_member(self,name):
        if not 0 <= self._position < len(self._rows):
            _field(self._manager._defaults(),name); return None
        return _field(self._manager._fields(self._rows[self._position]),name)
    def __str__(self): return str(self._selection_type)
