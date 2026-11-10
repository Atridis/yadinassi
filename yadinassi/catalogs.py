"""Catalog managers and editable objects over the logical application backend.

No native file format adapter is reachable here. Backend keys/revisions remain
opaque implementation identities, never native physical DataVersion claims.
"""
from decimal import Decimal
from datetime import datetime
from uuid import UUID, uuid4
from .dates import BSLDate, _date_from_datetime, _parts, TICKS_PER_SECOND
from .catalog_types import BSLCatalogReference, BSLCatalogType
from .catalog_backend import CatalogKey, CatalogDraft, CatalogSelection, CatalogScanRequest, CatalogComparison, Revision, BackendError, CatalogValuePage, CatalogValueRow, CatalogWriteOutcome
from .catalog_sections import BSLCatalogSection, _MAX_ROWS as _MAX_SECTION_ROWS, _MAX_BUFFER_BYTES
from .catalog_backend import CatalogCard, TabularSectionRows
from .catalog_qualifiers import normalize_field, normalize_string, validate_string
from .unique_identifiers import BSLUUID
from .values import BSLObject, HostFunction

_OMITTED=object()
_ZERO=UUID(int=0)
_ALIASES={'код':'code','наименование':'description','ссылка':'ref','пометкаудаления':'deletionmark'}


def _field(fields,name):
    if type(name) is not str:raise TypeError('catalog field name requires String')
    key=_ALIASES.get(name.casefold(),name.casefold())
    if 'parent' in fields: key={'родитель':'parent','этогруппа':'isfolder'}.get(key,key)
    if key not in fields:raise ValueError('catalog field not found: '+name)
    return fields[key]


class BSLCatalogs(BSLObject):
    def __init__(self,metadata,context):
        self._metadata,self._context=metadata,context
        self._managers={}
    def get_member(self,name):return self.get_index(name)
    def get_index(self,name):
        if type(name) is not str:raise TypeError('catalog name requires String')
        item=self._metadata._snapshot().get(name.casefold())
        if item is None:raise ValueError('catalog name not found')
        key=item._name.casefold()
        if key not in self._managers:self._managers[key]=BSLCatalogManager(self,item)
        return self._managers[key]
    def _manager_by_metadata_uuid(self,identity):
        matches=[item for item in self._metadata._snapshot().values() if UUID(item._metadata_uuid)==identity]
        if len(matches)!=1:raise ValueError('catalog target identity not found')
        return self.get_index(matches[0]._name)
    def set_index(self,name,value):raise ValueError('catalog managers are read-only')
    def type_by_name(self,name):
        from .type_values import type_by_name
        if type(name) is str:
            prefix,separator,catalog=name.partition('.')
            families={'catalogref':'_value_type','справочникссылка':'_value_type',
                      'catalogmanager':'_manager_type','справочникменеджер':'_manager_type',
                      'catalogselection':'_selection_type','справочниквыборка':'_selection_type',
                      'catalogobject':'_object_type','справочникобъект':'_object_type'}
            if separator and prefix.casefold() in families:return getattr(self.get_index(catalog),families[prefix.casefold()])
        return type_by_name(name)
    def __str__(self):return 'Справочники менеджер'


class BSLCatalogManager(BSLObject):
    def __init__(self,catalogs,metadata):
        self._catalogs,self._metadata=catalogs,metadata
        self._schema=metadata._schema
        for attr,family in (('_value_type','ref'),('_manager_type','manager'),('_selection_type','selection'),('_object_type','object')):
            setattr(self,attr,BSLCatalogType(self._schema.identity,self._schema.name,catalogs._metadata,family))
    @property
    def _backend(self):return self._catalogs._context.backend
    def _view(self):
        view=self._backend.begin_read()
        try:
            if (view.database_id!=self._catalogs._metadata._database_id
                    or view.configuration_generation!=self._catalogs._metadata._generation
                    or view.catalog_schema(self._schema.identity)!=self._schema):raise BackendError('schema_changed')
        except BaseException:
            view.close();raise
        return view
    def _key(self,record):return CatalogKey(self._catalogs._metadata._database_id,self._schema.identity,record)
    def _ref(self,record):return BSLCatalogReference(self._value_type,record,self._metadata,self._read_member,self._get_object)
    def empty_ref(self):return self._ref(_ZERO)
    def get_ref(self,uuid=_OMITTED):
        if uuid is _OMITTED or uuid is None:uuid=BSLUUID()
        if type(uuid) is not BSLUUID:raise TypeError('GetRef requires UUID')
        return self._ref(UUID(uuid.text))
    def _logical(self,field,value):
        if field.kind=='datetime':
            if type(value) is not datetime or value.tzinfo is not None or value.microsecond:raise ValueError('invalid backend date')
            return _date_from_datetime(value)
        if field.kind=='catalog_ref':
            if (type(value) is not CatalogKey or value.database_id!=self._key(_ZERO).database_id
                    or value.catalog_id!=field.target_catalog_id):raise ValueError('invalid backend reference')
            return self._catalogs._manager_by_metadata_uuid(value.catalog_id)._ref(value.record_id)
        expected={'string':str,'number':Decimal,'boolean':bool}.get(field.kind)
        if type(value) is not expected:raise TypeError('invalid backend scalar')
        return value
    def _stored(self,field,value):
        if field.kind=='datetime':
            if type(value) is not BSLDate:raise TypeError('Date field requires Date')
            value.require_known()
            if value.ticks%TICKS_PER_SECOND:raise ValueError('subsecond field value unsupported')
            return _parts(value)
        if field.kind=='catalog_ref':
            if (type(value) is not BSLCatalogReference or value.value_type.snapshot is not self._catalogs._metadata
                    or value.value_type.metadata_uuid!=field.target_catalog_id):raise TypeError('reference field requires same database target')
            return CatalogKey(self._key(_ZERO).database_id,field.target_catalog_id,value.reference_uuid)
        expected={'string':str,'number':Decimal,'boolean':bool}.get(field.kind)
        if type(value) is not expected:raise TypeError('catalog field type mismatch')
        if field.kind=='number' and not value.is_finite():raise ValueError('finite Number required')
        return value
    def _field_default(self,field):
        if field.kind=='catalog_ref':return self._catalogs._manager_by_metadata_uuid(field.target_catalog_id).empty_ref()
        if field.kind=='datetime':return BSLDate(0)
        return {'string':'','number':Decimal(0),'boolean':False}[field.kind]
    def _assigned(self,field,value):
        self._stored(field,value)
        return normalize_field(value,field)
    def _defaults(self,ref=None):
        values={'code':'','description':'','deletionmark':False,'ref':ref}
        if self._schema.hierarchy != 'none': values.update(parent=self.empty_ref(),isfolder=False)
        values.update((f.name.casefold(),self._field_default(f)) for f in self._schema.fields)
        return values
    def _fields(self,card):
        if card.key.database_id!=self._key(_ZERO).database_id or card.key.catalog_id!=self._schema.identity or len(card.values)!=len(self._schema.fields):raise BackendError('integrity')
        values={'code':card.code,'description':card.description,'deletionmark':card.deletion_mark,'ref':self._ref(card.key.record_id)}
        if self._schema.hierarchy != 'none':
            if type(card.is_folder) is not bool or (card.parent is not None and (type(card.parent) is not CatalogKey or card.parent.database_id!=card.key.database_id or card.parent.catalog_id!=card.key.catalog_id)):
                raise BackendError('integrity')
            values.update(parent=self._ref(_ZERO if card.parent is None else card.parent.record_id),isfolder=card.is_folder)
        values.update((f.name.casefold(),self._logical(f,v)) for f,v in zip(self._schema.fields,card.values))
        return values
    def _read(self,record):
        view=self._view()
        try:return view.read_catalog(self._key(record))
        finally:view.close()
    def _read_member(self,ref,name):
        card=self._read(ref.reference_uuid)
        return _field(self._defaults(ref) if card is None else self._fields(card),name)
    def _get_object(self,ref):
        card=self._read(ref.reference_uuid)
        return None if card is None else BSLCatalogObject(self,card)
    def create_item(self):
        if not self._backend.capabilities().catalog_create:raise BackendError('unsupported')
        return BSLCatalogObject(self)
    def create_folder(self):
        if self._schema.hierarchy != "groups_v1": raise BackendError("unsupported")
        result=self.create_item();result._values["isfolder"]=True
        return result
    def select(self):
        view=self._view()
        try:rows=view.select_catalog(self._schema.identity,CatalogSelection())
        finally:view.close()
        return BSLCatalogSelection(self,rows)
    def _find(self,field,value):
        view=self._view()
        try:
            page=view.scan_catalog_values(self._schema.identity,CatalogScanRequest(
                predicate=CatalogComparison(field,'eq',value),page_size=2),('ref',))
            if (type(page) is not CatalogValuePage or type(page.rows) is not tuple or len(page.rows)>2
                    or (page.continuation is not None and (type(page.continuation) is not str or len(page.continuation)!=32))):
                raise BackendError('integrity')
            matches=page.rows
            for row in matches:
                if (type(row) is not CatalogValueRow or type(row.key) is not CatalogKey
                        or any(type(item) is not UUID for item in (row.key.database_id,row.key.catalog_id,row.key.record_id))
                        or row.key.database_id!=view.database_id or row.key.catalog_id!=self._schema.identity
                        or type(row.key.record_id) is not UUID or not row.key.record_id.int
                        or type(row.values) is not tuple or len(row.values)!=1 or type(row.values[0]) is not CatalogKey
                        or any(type(item) is not UUID for item in (row.values[0].database_id,row.values[0].catalog_id,row.values[0].record_id))
                        or row.values[0]!=row.key):
                    raise BackendError('integrity')
            if page.continuation is not None:raise ValueError('ambiguous exact catalog lookup')
        finally:view.close()
        if len(matches)>1:raise ValueError('ambiguous exact catalog lookup')
        return self._ref(matches[0].key.record_id) if matches else self.empty_ref()
    def find_by_code(self,code):
        if type(code) is not str:raise TypeError('String Code required')
        return self._find('code',code)
    def find_by_description(self,description,exact=_OMITTED):
        if type(description) is not str or exact is not True:raise ValueError('explicit exact String description lookup required')
        return self._find('description',description)
    def get_member(self,name):
        methods={'emptyref':self.empty_ref,'пустаяссылка':self.empty_ref,'getref':self.get_ref,'получитьссылку':self.get_ref,
                 'select':self.select,'выбрать':self.select,'findbycode':self.find_by_code,'найтипокоду':self.find_by_code,
                 'findbydescription':self.find_by_description,'найтипонаименованию':self.find_by_description,
                 'createitem':self.create_item,'создатьэлемент':self.create_item,
                 'createfolder':self.create_folder,'создатьгруппу':self.create_folder}
        method=methods.get(name.casefold())
        return HostFunction(name,method) if method else super().get_member(name)
    def __str__(self):return str(self._manager_type)


class BSLCatalogObject(BSLObject):
    """Detached edit buffer: only successful backend commit changes IsNew/revision."""
    def __init__(self,manager,card=None):
        self._manager=manager;self._object_type=manager._object_type
        if manager._schema.tabular_sections and not manager._backend.capabilities().catalog_tabular_sections:
            raise BackendError('unsupported')
        self._key=manager._key(uuid4()) if card is None else card.key
        self._revision=None if card is None else card.revision
        self._values=manager._defaults(manager.empty_ref()) if card is None else manager._fields(card)
        self._operation_id=uuid4()
        self._pending_write=None
        self._pending_preparation=None
        self._sections={}
        if card is not None and (type(card.tabular_sections) is not tuple
                or any(type(s) is not TabularSectionRows for s in card.tabular_sections)):
            raise BackendError('integrity')
        contents={} if card is None else {s.section_id:s for s in card.tabular_sections}
        if card is not None and (len(contents)!=len(card.tabular_sections)
                or set(contents)!={s.identity for s in manager._schema.tabular_sections}):
            raise BackendError('integrity')
        reserved=set(self._values)|{'write','записать','isnew','этоновый','setnewobjectref',
            'установитьссылкунового','metadata','метаданные'}|set(_ALIASES)
        for schema in manager._schema.tabular_sections:
            name=schema.name.casefold()
            if name in reserved or name in self._sections:raise BackendError('unsupported')
            self._sections[name]=BSLCatalogSection(self,schema,() if card is None else contents[schema.identity].rows)
        if self._section_row_count()>_MAX_SECTION_ROWS or self._section_buffer_bytes()>_MAX_BUFFER_BYTES:
            raise BackendError('unsupported')
    def _section_row_count(self):return sum(len(section._rows) for section in self._sections.values())
    def _section_buffer_bytes(self):return sum(section._bytes for section in self._sections.values())
    def _section_draft(self):
        if not any(section._dirty for section in self._sections.values()):return None
        return tuple(section._stored_rows() for section in self._sections.values())
    def is_new(self):return self._revision is None
    def set_new_object_ref(self,ref):
        if self._pending_write is not None:raise BackendError('uncertain_commit')
        if not self.is_new():raise ValueError('object already persisted')
        if type(ref) is not BSLCatalogReference or ref.value_type!=self._manager._value_type or ref.is_empty():raise TypeError('new nonempty same-catalog reference required')
        self._key=self._manager._key(ref.reference_uuid)
    def _accept_revision(self,revision,code=None):
        m=self._manager
        if (type(revision) is not Revision or
                (revision.database_id,revision.configuration_generation,revision.catalog_id,revision.record_id) !=
                (self._key.database_id,m._catalogs._metadata._generation,self._key.catalog_id,self._key.record_id)):
            raise BackendError('uncertain_commit')
        ref=m._ref(self._key.record_id);next_operation=uuid4()
        values=dict(self._values);values['ref']=ref
        if code is not None:values['code']=code
        self._revision=revision
        self._values=values
        self._operation_id=next_operation
        # Keep the exact intent locked until every section has accepted it.
        for section in self._sections.values():section._dirty=False
        self._pending_write=None
        self._pending_preparation=None

    def _accept_outcome(self,outcome):
        if type(outcome) is not CatalogWriteOutcome or self._pending_write is None:
            raise BackendError('uncertain_commit')
        draft=self._pending_write[0]
        try:validate_string(outcome.code,self._manager._schema.code_length)
        except (TypeError,ValueError):raise BackendError('uncertain_commit') from None
        if draft.auto_number:
            if (len(outcome.code)!=self._manager._schema.code_length or not outcome.code.isascii()
                    or not outcome.code.isdecimal() or int(outcome.code)==0):
                raise BackendError('uncertain_commit')
        elif outcome.code!=draft.code:raise BackendError('uncertain_commit')
        self._accept_revision(outcome.revision,outcome.code)

    def write(self):
        self._write()
        return None

    def _write_draft(self, *, complete_sections=False):
        m=self._manager
        sections=(tuple(section._stored_rows() for section in self._sections.values())
                  if complete_sections else self._section_draft())
        return CatalogDraft(self._key,self._values['code'],self._values['description'],self._values['deletionmark'],
                            tuple(m._stored(f,self._values[f.name.casefold()]) for f in m._schema.fields),sections,
                            auto_number=self.is_new() and m._schema.numbering=='decimal_v1' and self._values['code']=='',
                            parent=(None if m._schema.hierarchy=='none' or self._values['parent'].is_empty() else m._key(self._values['parent'].reference_uuid)),
                            is_folder=self._values['isfolder'] if m._schema.hierarchy!='none' else False)

    def _write(self, *, preparation=None):
        """Shared host writer. Preparation is never an exposed BSL argument."""
        m=self._manager;caps=m._backend.capabilities()
        if m._schema.tabular_sections and not caps.catalog_tabular_sections:raise BackendError('unsupported')
        if not caps.atomic_transactions or not (caps.catalog_create if self.is_new() else caps.catalog_update):raise BackendError('unsupported')
        outcomes=caps.catalog_write_outcomes
        if m._schema.numbering!='explicit' and not outcomes:raise BackendError('unsupported')
        if self._pending_preparation is not None:
            retained,backend=self._pending_preparation
            if m._backend is not backend:raise BackendError('schema_changed')
            if preparation is not None and preparation!=retained:
                raise BackendError('uncertain_commit')
            preparation=retained
        elif self._pending_write is not None and preparation is not None:
            # Never reinterpret a previously submitted ordinary write as one
            # protected by a new source/validation contract.
            raise BackendError('uncertain_commit')
        if self._pending_write is None:
            policy = getattr(m._backend, 'catalog_write_preparation', None)
            source = policy(m._schema.identity) if policy is not None else None
            if source is not None:
                if preparation is not None and preparation[0] != source:
                    raise BackendError('schema_changed')
                preparation = (source, preparation[1] if preparation is not None else False)
        retry=self._pending_write is not None
        if self._pending_write is not None:
            draft,expected,operation=self._pending_write
            revision=(m._backend.resolve_write_outcome(operation,draft,expected) if outcomes
                      else m._backend.resolve_write(operation,draft,expected))
            if revision is not None:
                if outcomes:self._accept_outcome(revision)
                else:self._accept_revision(revision)
                return ()
        else:
            draft=self._write_draft(complete_sections=preparation is not None)
            expected=self._revision
            operation=self._operation_id
        tx=m._backend.begin_write(operation)
        committing=False
        messages=()
        try:
            if tx.database_id!=self._key.database_id or tx.configuration_generation!=m._catalogs._metadata._generation or tx.catalog_schema(m._schema.identity)!=m._schema:raise BackendError('schema_changed')
            if preparation is not None:
                from .catalog_object_preparation import _prepare_catalog_object, CatalogWriteRefused
                if retry:
                    # Receipt absence is already proved. Validate the frozen
                    # submitted image, never a newly edited buffer or source.
                    card=CatalogCard(draft.key,expected,draft.code,draft.description,
                                     draft.deletion_mark,draft.values,draft.tabular_sections,draft.parent,draft.is_folder)
                    candidate=BSLCatalogObject(m,card)
                    if expected is None:candidate._values['ref']=m.empty_ref()
                else:
                    candidate=self
                cancel,messages=_prepare_catalog_object(preparation[0],candidate,
                    cancel=preparation[1],write_view=tx)
                if cancel:raise CatalogWriteRefused(messages)
                prepared=candidate._write_draft(complete_sections=True)
                if retry and prepared!=draft:
                    raise BackendError('conflict')
                draft=prepared
            if expected is None:tx.create(draft)
            else:tx.update(draft,expected)
            # Keep the exact submitted intent across an uncertain commit response.
            self._pending_write=(draft,expected,operation)
            self._pending_preparation=(preparation,m._backend) if preparation is not None else None
            committing=True
            revisions=tx.commit_outcomes() if outcomes else tx.commit()
            if len(revisions)!=1:raise BackendError('uncertain_commit')
            tx.close()  # Cleanup must complete before the revision is accepted.
            if outcomes:self._accept_outcome(revisions[0])
            else:self._accept_revision(revisions[0])
        except BaseException as error:
            if not committing:
                self._pending_write=None
                self._pending_preparation=None
            for cleanup in (tx.rollback,tx.close):
                try:cleanup()
                except BaseException as cleanup_error:
                    if ((not isinstance(cleanup_error,Exception) or isinstance(cleanup_error,MemoryError)) and
                            isinstance(error,Exception) and not isinstance(error,MemoryError)):
                        error=cleanup_error
            if committing and isinstance(error,Exception) and not isinstance(error,MemoryError):
                raise BackendError('uncertain_commit') from None
            raise error
        return messages
    def get_member(self,name):
        key=name.casefold()
        methods={'write':self.write,'записать':self.write,'isnew':self.is_new,'этоновый':self.is_new,
            'setnewobjectref':self.set_new_object_ref,'установитьссылкунового':self.set_new_object_ref,
            'metadata':lambda:self._manager._metadata,'метаданные':lambda:self._manager._metadata}
        if key in methods:return HostFunction(name,methods[key])
        if key in self._sections:return self._sections[key]
        return _field(self._values,name)
    def set_member(self,name,value):
        if self._pending_write is not None:raise BackendError('uncertain_commit')
        key=_ALIASES.get(name.casefold(),name.casefold())
        if self._manager._schema.hierarchy!='none': key={'родитель':'parent','этогруппа':'isfolder'}.get(key,key)
        if key in self._sections:raise ValueError('tabular section replacement is unsupported')
        if key=='ref' or (key=='isfolder' and self._manager._schema.hierarchy!='none'):raise ValueError('Ref and IsFolder are read-only')
        if key not in self._values:raise ValueError('catalog field not found')
        if key in ('code','description'):
            length=self._manager._schema.code_length if key=='code' else self._manager._schema.description_length
            value=normalize_string(value,length)
        elif key=='parent' and self._manager._schema.hierarchy!='none':
            if type(value) is not BSLCatalogReference or value.value_type!=self._manager._value_type: raise TypeError('Parent requires same-catalog reference')
        elif key=='deletionmark':
            if type(value) is not bool:raise TypeError('DeletionMark requires Boolean')
        else:
            f=next(f for f in self._manager._schema.fields if f.name.casefold()==key)
            value=self._manager._assigned(f,value)
        self._values[key]=value
    def __str__(self):return self._values['description']


class BSLCatalogSelection(BSLObject):
    def __init__(self,manager,rows):
        self._manager=manager;self._selection_type=manager._selection_type
        self._rows=tuple(rows);self._position=-1;self._next_position=0
    def next(self):
        if self._next_position>=len(self._rows):self._next_position=0;return False
        self._position=self._next_position;self._next_position+=1;return True
    def get_method(self,name):
        if name.casefold() in ('next','следующий'):return HostFunction(name,self.next)
        if name.casefold() in ('getobject','получитьобъект'):
            return HostFunction(name,lambda:None if self._position<0 else self._manager._get_object(self._manager._ref(self._rows[self._position].key.record_id)))
        return super().get_method(name)
    def get_member(self,name):
        if self._position<0:_field(self._manager._defaults(),name);return None
        return _field(self._manager._fields(self._rows[self._position]),name)
    def __str__(self):return str(self._selection_type)
