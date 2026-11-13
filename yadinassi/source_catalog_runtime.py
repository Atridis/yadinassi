"""Explicit v4 source catalog objects with actual-caller authorization."""
from uuid import UUID, uuid4
from .values import BSLObject, HostFunction
from .source_references import SourceReferenceManager
from .source_constant_store import _encode

_ALIASES={'код':'code','наименование':'description','пометкаудаления':'deletionmark','ссылка':'ref'}
_OBJECT_METHODS={'read':'read','прочитать':'read','write':'write','записать':'write','isnew':'new','этоновый':'new','metadata':'metadata','метаданные':'metadata'}
_MANAGER_METHODS={'createitem':'create','создатьэлемент':'create','select':'select','выбрать':'select'}


def store_for(manager, caller):
    from .safe_mode import require_external_access
    from .source_catalog_store import SourceCatalogStore
    app=manager.authorize(caller)
    if caller._scheduler.pending:
        raise ValueError("source catalog operations require no pending asynchronous tasks")
    require_external_access('source catalog database')
    if manager.family!='Catalog' or type(app.constant_store) is not SourceCatalogStore:
        raise ValueError('source Catalog records require explicit v4 scratch capability')
    app.constant_store.catalog(manager.name)
    return app,app.constant_store


class SourceCatalogObject(BSLObject):
    def __init__(self, manager, definition, identity=None, revision=0, values=None):
        self.manager,self.definition=manager,definition
        self.identity=identity or uuid4();self.revision=revision
        self.values=dict(values) if values is not None else {'code':'','description':'','deletionmark':False}
        self.fields={f.name.casefold():f for f in definition.fields}

    def property_read(self, caller, name):
        app,_=store_for(self.manager,caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key in _OBJECT_METHODS:return self.get_member(name)
        if key=='ref':return app.references.ref('Catalog',self.manager.name,self.identity if self.revision else UUID(int=0))
        if key not in self.fields:raise ValueError('unknown source catalog field: '+name)
        if key not in self.values:raise ValueError('source catalog field requires explicit assignment: '+name)
        return self.values[key]

    def property_write(self, caller, name, value):
        store_for(self.manager,caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key not in self.fields:raise ValueError('source catalog field is readonly or unknown: '+name)
        _encode(value,self.fields[key]);self.values[key]=value

    def get_member(self,name):
        operation=_OBJECT_METHODS.get(name.casefold())
        if operation is None:raise ValueError('source object fields require interpreter access')
        return HostFunction(name,SourceCatalogCall(self,operation),returns_value=operation not in ('read','write'))


class SourceCatalogSelection(BSLObject):
    def __init__(self,manager,rows):
        self.manager,self.rows,self.index=manager,rows,-1

    def property_read(self,caller,name):
        app,_=store_for(self.manager,caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key in ('next','следующий','getobject','получитьобъект'):return self.get_member(name)
        if not 0<=self.index<len(self.rows):raise ValueError('source selection is not positioned')
        identity,_,values=self.rows[self.index]
        if key=='ref':return app.references.ref('Catalog',self.manager.name,identity)
        if key not in values:raise ValueError('unknown source selection field: '+name)
        return values[key]

    def property_write(self,caller,name,value):
        store_for(self.manager,caller)
        raise ValueError("source catalog selection is readonly")

    def get_member(self,name):
        operation={'next':'next','следующий':'next','getobject':'object','получитьобъект':'object'}.get(name.casefold())
        if operation is None:raise ValueError('source selection fields require interpreter access')
        return HostFunction(name,SourceCatalogCall(self,operation))


class SourceCatalogCall:
    def __init__(self,receiver,operation,identity=None):
        self.receiver,self.operation,self.identity=receiver,operation,identity

    def __call__(self,*args):raise ValueError('source catalog methods require interpreter invocation')

    def invoke(self,caller,values):
        receiver=self.receiver
        manager=receiver if type(receiver) is SourceReferenceManager else receiver.manager
        app,store=store_for(manager,caller)
        if values:raise TypeError('source catalog method supports no arguments in this profile')
        definition=store.catalog(manager.name)
        if self.operation=='create':return SourceCatalogObject(manager,definition)
        if self.operation=='select':return SourceCatalogSelection(manager,store.read_records(manager.name))
        if self.operation=='getobject':
            identity,revision,fields=store.read_records(manager.name,self.identity)[0]
            return SourceCatalogObject(manager,definition,identity,revision,fields)
        if self.operation=='next':
            receiver.index+=1
            return receiver.index<len(receiver.rows)
        if self.operation=='object':
            if not 0<=receiver.index<len(receiver.rows):raise ValueError('source selection is not positioned')
            identity,revision,fields=receiver.rows[receiver.index]
            return SourceCatalogObject(manager,definition,identity,revision,fields)
        if self.operation=='new':return receiver.revision==0
        if self.operation=='metadata':return app.references.definition('Catalog',manager.name)[2]
        if self.operation=='read':
            identity,revision,fields=store.read_records(manager.name,receiver.identity)[0]
            receiver.values,receiver.revision=fields,revision
            return None
        if self.operation=='write':
            receiver.revision=store.write_record(manager.name,receiver.identity,receiver.revision,receiver.values)
            return None
        raise ValueError('unsupported source catalog operation')


def reference_call(caller, receiver, name):
    from .catalog_types import BSLCatalogReference
    app=getattr(caller,'application',None)
    if type(receiver) is not BSLCatalogReference or app is None or receiver.value_type.snapshot is not app.references.snapshot:
        return None
    if name.casefold() not in ('getobject','получитьобъект'):
        return None
    manager=SourceReferenceManager(app,'Catalog',receiver.value_type.name)
    return HostFunction(name,SourceCatalogCall(manager,'getobject',receiver.reference_uuid))
