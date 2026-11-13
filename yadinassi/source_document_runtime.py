"""Explicit nonposting document objects; no module activation or fabricated data."""
from uuid import UUID, uuid4
from .values import BSLObject, HostFunction
from .source_references import SourceReferenceManager
from .source_constant_store import _encode

_ALIASES={'номер':'number','дата':'date','пометкаудаления':'deletionmark','проведен':'posted','ссылка':'ref'}
_OBJECT_METHODS={'read':'read','прочитать':'read','write':'write','записать':'write','isnew':'new','этоновый':'new','metadata':'metadata','метаданные':'metadata'}
_MANAGER_METHODS={'createdocument':'create','создатьдокумент':'create','select':'select','выбрать':'select'}


def store_for(manager,caller):
    from .safe_mode import require_external_access
    from .source_document_store import SourceDocumentStore
    from .source_catalog_runtime import _constructing, _active_write
    from .source_constant_managers import _active_write as constant_write, _constructing as constant_construction
    app=manager.authorize(caller)
    if caller._scheduler.pending:raise ValueError('source document operations require no pending asynchronous tasks')
    require_external_access('source document database')
    if manager.family!='Document' or type(app.constant_store) is not SourceDocumentStore:
        raise ValueError('source Document records require explicit v5 scratch capability')
    app.constant_store.document(manager.name)
    if (_constructing.get() or _active_write.get() or constant_write.get() or constant_construction.get()) and not app.constant_store.transaction_active:
        raise ValueError('source lifecycle transaction aborted; document access refused')
    return app,app.constant_store


class SourceDocumentObject(BSLObject):
    def __init__(self,manager,definition,identity=None,revision=0,values=None):
        self.manager,self.definition=manager,definition
        self.identity=identity or uuid4();self.revision=revision
        self.values=dict(values) if values is not None else {'number':'','deletionmark':False,'posted':False}
        self.fields={f.name.casefold():f for f in definition.fields}

    def authorize(self,caller):return store_for(self.manager,caller)

    def property_read(self,caller,name):
        app,_=self.authorize(caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key in _OBJECT_METHODS:return self.get_member(name)
        if key=='ref':return app.references.ref('Document',self.manager.name,self.identity if self.revision else UUID(int=0))
        if key not in self.fields:raise ValueError('unknown source document field: '+name)
        if key not in self.values:raise ValueError('source document field requires explicit assignment: '+name)
        return self.values[key]

    def property_write(self,caller,name,value):
        self.authorize(caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key not in self.fields or key=='posted':raise ValueError('source document field readonly or unknown: '+name)
        _encode(value,self.fields[key]);self.values[key]=value

    def get_member(self,name):
        operation=_OBJECT_METHODS.get(name.casefold())
        if operation is None:raise ValueError('source document fields require interpreter access')
        return HostFunction(name,SourceDocumentCall(self,operation),returns_value=operation not in ('read','write'))


class SourceDocumentSelection(BSLObject):
    def __init__(self,manager,rows):
        self.manager,self.rows,self.index=manager,rows,-1

    def property_read(self,caller,name):
        app,_=store_for(self.manager,caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key in ('next','следующий','getobject','получитьобъект'):return self.get_member(name)
        if not 0<=self.index<len(self.rows):raise ValueError('source selection is not positioned')
        identity,_,values=self.rows[self.index]
        if key=='ref':return app.references.ref('Document',self.manager.name,identity)
        if key not in values:raise ValueError('unknown source selection field: '+name)
        return values[key]

    def property_write(self,caller,name,value):
        store_for(self.manager,caller)
        raise ValueError("source document selection is readonly")

    def get_member(self,name):
        operation={'next':'next','следующий':'next','getobject':'object','получитьобъект':'object'}.get(name.casefold())
        if operation is None:raise ValueError('source selection fields require interpreter access')
        return HostFunction(name,SourceDocumentCall(self,operation))


class SourceDocumentCall:
    def __init__(self,receiver,operation,identity=None):
        self.receiver,self.operation,self.identity=receiver,operation,identity
    def __call__(self,*args):raise ValueError('source document methods require interpreter invocation')
    def invoke(self,caller,values):
        receiver=self.receiver
        manager=receiver if type(receiver) is SourceReferenceManager else receiver.manager
        app,store=store_for(manager,caller);definition=store.document(manager.name)
        if values:raise TypeError('source document methods accept no arguments; posting unsupported')
        if self.operation=='create':return SourceDocumentObject(manager,definition)
        if self.operation=='select':return SourceDocumentSelection(manager,store.read_documents(manager.name))
        if self.operation=='getobject':
            identity,revision,fields=store.read_documents(manager.name,self.identity)[0]
            return SourceDocumentObject(manager,definition,identity,revision,fields)
        if self.operation=='next':
            receiver.index+=1;return receiver.index<len(receiver.rows)
        if self.operation=='object':
            if not 0<=receiver.index<len(receiver.rows):raise ValueError('source selection is not positioned')
            identity,revision,fields=receiver.rows[receiver.index]
            return SourceDocumentObject(manager,definition,identity,revision,fields)
        receiver.authorize(caller)
        if self.operation=='new':return receiver.revision==0
        if self.operation=='metadata':return app.references.definition('Document',manager.name)[2]
        if self.operation=='read':
            _,revision,fields=store.read_documents(manager.name,receiver.identity)[0]
            receiver.values,receiver.revision=fields,revision;return None
        if self.operation=='write':
            receiver.revision=store.write_document(manager.name,receiver.identity,receiver.revision,receiver.values)
            return None
        raise ValueError('unsupported source document operation')


_NEUTRAL_REF_MEMBERS={'ref','ссылка','isempty','пустая','uuid','уникальныйидентификатор','metadata','метаданные'}


def is_source_reference(value):
    from .document_types import BSLDocumentReference
    from .configuration_source_metadata import SourceMetadataObject
    from .source_references import _SourceReferenceSnapshot
    return (type(value) is BSLDocumentReference and
            (type(value.value_type.snapshot) is _SourceReferenceSnapshot or type(value.metadata) is SourceMetadataObject))


def _reference_manager(caller,receiver):
    app=getattr(caller,'application',None)
    if app is None:
        raise ValueError('source reference requires owning application context')
    app.require_open()
    entry,canonical,metadata=app.references.definition('Document',receiver.value_type.name)
    if (receiver.value_type is not canonical or receiver.metadata is not metadata
            or receiver.value_type.snapshot is not app.references.snapshot
            or type(receiver.reference_uuid) is not UUID
            or receiver.read_member is not None or receiver.get_object is not None):
        raise TypeError('source reference requires canonical owned identity without callbacks')
    manager=SourceReferenceManager(app,'Document',entry.name)
    manager.authorize(caller)
    return manager


def reference_member(caller,receiver,name):
    if name.casefold() in _NEUTRAL_REF_MEMBERS:
        return receiver.get_member(name)
    if name.casefold() in ('getobject','получитьобъект'):
        return reference_call(caller,receiver,name)
    manager=_reference_manager(caller,receiver)
    _,store=store_for(manager,caller)
    definition=store.document(manager.name)
    key=_ALIASES.get(name.casefold(),name.casefold())
    if key not in {f.name.casefold() for f in definition.fields}:
        raise ValueError('unknown source reference field: '+name)
    return store.read_documents(manager.name,receiver.reference_uuid)[0][2][key]


def readonly_reference(caller,receiver,name,value):
    _reference_manager(caller,receiver)
    raise ValueError('source reference fields are readonly; use GetObject().Write()')


def reference_call(caller,receiver,name):
    if not is_source_reference(receiver):return None
    if name.casefold() in _NEUTRAL_REF_MEMBERS:
        return receiver.get_method(name)
    manager=_reference_manager(caller,receiver)
    if name.casefold() not in ('getobject','получитьобъект'):
        raise ValueError('unsupported source reference method: '+name)
    return HostFunction(name,SourceDocumentCall(manager,'getobject',receiver.reference_uuid))
