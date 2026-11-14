"""Explicit v4 source catalog objects with actual-caller authorization."""
from uuid import UUID, uuid4
from contextvars import ContextVar
from .syntax import ast
from .configuration_source_runtime import _SourceInterpreter

_constructing = ContextVar("source_catalog_construction", default=())
_active_write = ContextVar("source_catalog_write", default=False)
from .values import BSLObject, HostFunction
from .source_references import SourceReferenceManager
from .source_constant_store import _encode

_ALIASES={'код':'code','наименование':'description','пометкаудаления':'deletionmark','ссылка':'ref'}
_OBJECT_METHODS={'read':'read','прочитать':'read','write':'write','записать':'write','isnew':'new','этоновый':'new','metadata':'metadata','метаданные':'metadata'}
_MANAGER_METHODS={'createitem':'create','создатьэлемент':'create','select':'select','выбрать':'select',
    'findbycode':'findcode','найтипокоду':'findcode','findbydescription':'finddescription',
    'найтипонаименованию':'finddescription','findbyattribute':'findattribute','найтипореквизиту':'findattribute'}


def store_for(manager, caller):
    from .safe_mode import require_external_access
    from .source_catalog_store import SourceCatalogStore
    from .source_document_store import SourceDocumentStore
    from .source_document_section_store import SourceDocumentSectionStore
    app=manager.authorize(caller)
    if caller._scheduler.pending:
        raise ValueError("source catalog operations require no pending asynchronous tasks")
    require_external_access('source catalog database')
    if manager.family!='Catalog' or type(app.constant_store) not in (SourceCatalogStore, SourceDocumentStore, SourceDocumentSectionStore):
        raise ValueError('source Catalog records require explicit v4 scratch capability')
    app.constant_store.catalog(manager.name)
    from .source_constant_managers import _active_write as constant_write, _constructing as constant_construction
    from .source_document_runtime import _active_write as document_write, _constructing as document_construction
    if (_constructing.get() or _active_write.get() or constant_write.get() or constant_construction.get() or document_write.get() or document_construction.get()) and not app.constant_store.transaction_active:
        raise ValueError("source lifecycle transaction aborted; catalog access refused")
    return app,app.constant_store


class SourceCatalogObject(BSLObject):
    def __init__(self, manager, definition, identity=None, revision=0, values=None):
        self.manager,self.definition=manager,definition
        self.identity=identity or uuid4();self.revision=revision
        self.values=dict(values) if values is not None else {'code':'','description':'','deletionmark':False}
        self.fields={f.name.casefold():f for f in definition.fields}
        self.interpreter=None
        self._ready=True
        self._closed=False

    def property_read(self, caller, name):
        app,_=self.authorize(caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key in _OBJECT_METHODS:return self.get_member(name)
        if key=='ref':return app.references.ref('Catalog',self.manager.name,self.identity if self.revision else UUID(int=0))
        if key not in self.fields:
            if self.interpreter is not None:
                return self.interpreter._self_module.get_member(name)
            raise ValueError('unknown source catalog field: '+name)
        if key not in self.values:raise ValueError('source catalog field requires explicit assignment: '+name)
        return self.values[key]

    def property_write(self, caller, name, value):
        self.authorize(caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key not in self.fields:
            if self.interpreter is not None and key not in _OBJECT_METHODS and key not in ('ref','thisobject','этотобъект'):
                return self.interpreter._self_module.set_member(name,value)
            raise ValueError('source catalog field is readonly or unknown: '+name)
        _encode(value,self.fields[key]);self.values[key]=value

    def authorize(self,caller):
        app,store=store_for(self.manager,caller)
        if self._closed or (not self._ready and caller is not self.interpreter):
            raise ValueError('catalog object initialization incomplete or failed')
        if self.interpreter is not None:self.interpreter._require_family()
        return app,store

    def exported_routine(self,caller,name):
        self.authorize(caller)
        if self.interpreter is None:
            raise ValueError('catalog object exported routine unavailable: '+name)
        return self.interpreter._self_module.routine(name)

    def event(self,caller,names):
        vm=self.interpreter
        if vm is None:return
        matches=[vm.server_routines[n] for n in names if n in vm.server_routines]
        if not matches:return
        routine=matches[0]
        vm.variables['__catalog_cancel']=False
        try:
            yield from vm.call_routine(routine,[ast.Name(routine.token,'__catalog_cancel')],vm,require_value=False)
            cancelled=vm.variables['__catalog_cancel']
            if type(cancelled) is not bool:raise TypeError('catalog event Cancel requires Boolean')
            if cancelled:raise ValueError('catalog write cancelled by handler')
        finally:
            vm.variables.pop('__catalog_cancel',None)

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
        definition=store.catalog(manager.name)
        if self.operation in ('findcode','finddescription','findattribute'):
            return find_reference(caller,manager,definition,self.operation,values)
        if values:raise TypeError('source catalog method supports no arguments in this profile')
        if self.operation=='create':return (yield from create_object(caller,manager,definition))
        if self.operation=='select':return SourceCatalogSelection(manager,store.read_records(manager.name))
        if self.operation=='getobject':
            identity,revision,fields=store.read_records(manager.name,self.identity)[0]
            return (yield from create_object(caller,manager,definition,identity,revision,fields))
        if self.operation=='next':
            receiver.index+=1
            return receiver.index<len(receiver.rows)
        if self.operation=='object':
            if not 0<=receiver.index<len(receiver.rows):raise ValueError('source selection is not positioned')
            identity,revision,fields=receiver.rows[receiver.index]
            return (yield from create_object(caller,manager,definition,identity,revision,fields))
        receiver.authorize(caller)
        if self.operation=='new':return receiver.revision==0
        if self.operation=='metadata':return app.references.definition('Catalog',manager.name)[2]
        if self.operation=='read':
            identity,revision,fields=store.read_records(manager.name,receiver.identity)[0]
            receiver.values,receiver.revision=fields,revision
            return None
        if self.operation=='write':
            yield from write_object(caller,receiver)
            return None
        raise ValueError('unsupported source catalog operation')


_NEUTRAL_REF_MEMBERS={'ref','ссылка','isempty','пустая','uuid','уникальныйидентификатор','metadata','метаданные'}


def is_source_reference(value):
    from .catalog_types import BSLCatalogReference
    from .configuration_source_metadata import SourceMetadataObject
    from .source_references import _SourceReferenceSnapshot
    return (type(value) is BSLCatalogReference and
            (type(value.value_type.snapshot) is _SourceReferenceSnapshot or type(value.metadata) is SourceMetadataObject))


def _reference_manager(caller,receiver):
    app=getattr(caller,'application',None)
    if app is None:
        raise ValueError('source reference requires owning application context')
    app.require_open()
    entry,canonical,metadata=app.references.definition('Catalog',receiver.value_type.name)
    if (receiver.value_type is not canonical or receiver.metadata is not metadata
            or receiver.value_type.snapshot is not app.references.snapshot
            or type(receiver.reference_uuid) is not UUID
            or receiver.read_member is not None or receiver.get_object is not None):
        raise TypeError('source reference requires canonical owned identity without callbacks')
    manager=SourceReferenceManager(app,'Catalog',entry.name)
    manager.authorize(caller)
    return manager


def reference_member(caller,receiver,name):
    if name.casefold() in _NEUTRAL_REF_MEMBERS:
        return receiver.get_member(name)
    if name.casefold() in ('getobject','получитьобъект'):
        return reference_call(caller,receiver,name)
    manager=_reference_manager(caller,receiver)
    _,store=store_for(manager,caller)
    definition=store.catalog(manager.name)
    key=_ALIASES.get(name.casefold(),name.casefold())
    if key not in {f.name.casefold() for f in definition.fields}:
        raise ValueError('unknown source reference field: '+name)
    return store.read_records(manager.name,receiver.reference_uuid)[0][2][key]


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
    return HostFunction(name,SourceCatalogCall(manager,'getobject',receiver.reference_uuid))


def find_reference(caller,manager,definition,operation,arguments):
    app,store=store_for(manager,caller)
    if operation=='findcode':
        if len(arguments)!=1:raise TypeError('FindByCode requires one explicit String code')
        key,value='code',arguments[0]
    elif operation=='finddescription':
        if len(arguments)!=2 or arguments[1] is not True:
            raise ValueError('FindByDescription requires explicit exact-match True; partial matching unsupported')
        key,value='description',arguments[0]
    else:
        if len(arguments)!=2 or type(arguments[0]) is not str or not 1<=len(arguments[0])<=128:
            raise TypeError('FindByAttribute requires a bounded field name and explicit typed value')
        key=_ALIASES.get(arguments[0].casefold(),arguments[0].casefold());value=arguments[1]
    fields={f.name.casefold():f for f in definition.fields}
    if key not in fields:raise ValueError('unknown source catalog lookup field')
    field=fields[key]
    _encode(value,field)
    if field.kind=='object_ref':
        if field.qualifiers[0]=='Document':
            from .source_document_runtime import _reference_manager as document_reference_manager
            document_reference_manager(caller,value)
        else:_reference_manager(caller,value)
    matches=[identity for identity,_,values in store.read_records(manager.name) if values[key]==value]
    if len(matches)>1:
        raise ValueError('ambiguous source catalog lookup; multiple exact matches')
    return app.references.ref('Catalog',manager.name,matches[0] if matches else UUID(int=0))


class _ObjectInterpreter(_SourceInterpreter):
    def __init__(self,obj,app):
        super().__init__(app,family_owner=app.interpreter,compilation_profile=app.compilation_profile)
        self.object=obj
        self._logical_side='server'

    def field(self,name):
        key=_ALIASES.get(name.casefold(),name.casefold())
        return key in self.object.fields or key=='ref'

    def visit_Name(self,node):
        if node.name.casefold() in ('thisobject','этотобъект'):return self.object
        if node.name.casefold() in _OBJECT_METHODS:return self.object.get_member(node.name)
        if self.field(node.name):return self.object.property_read(self,node.name)
        return super().visit_Name(node)

    def set_variable(self,name,value):
        if name.casefold() in ('thisobject','этотобъект'):
            raise ValueError('ThisObject is read-only')
        if self.field(name):return self.object.property_write(self,name,value)
        return super().set_variable(name,value)

    def argument(self,node):
        node=self.ungroup(node)
        from .runtime import _Reference
        if type(node) is ast.Name and node.name.casefold()=='__catalog_cancel':
            return _Reference(lambda:self.variables['__catalog_cancel'],
                              lambda value:self.variables.__setitem__('__catalog_cancel',value))
        if type(node) is ast.Name and self.field(node.name):
            self.object.property_read(self,node.name)
            return _Reference(lambda:self.object.property_read(self,node.name),
                              lambda value:self.object.property_write(self,node.name,value))
        return (yield from super().argument(node))


def create_object(caller,manager,definition,identity=None,revision=0,values=None):
    app,store=store_for(manager,caller)
    obj=SourceCatalogObject(manager,definition,identity)
    path=definition.object_module
    if path is not None:
        from .source_catalog_definitions import catalog_module_program
        program=catalog_module_program(app.files[path],path,definition.fields)
        stack=_constructing.get();key=(id(app),definition.identity)
        if key in stack or len(stack)>=32:
            raise ValueError('recursive or excessive catalog object initialization')
        vm=_ObjectInterpreter(obj,app);obj.interpreter=vm;obj._ready=False
        token=None;owned=not store.transaction_active
        from .database_transactions import admission
        from .safe_mode import routine_frame
        try:
            if owned:store.begin_transaction()
            token=_constructing.set((*stack,key))
            vm._self_module.ready=True
            with admission(False),routine_frame(caller,vm):
                yield from vm._execute_program(program)
            if not store.transaction_active:
                raise ValueError('catalog initialization transaction aborted')
            store_for(manager,caller)
            if owned:store.commit_transaction()
            obj._ready=True
        except BaseException:
            obj._closed=True
            if store.transaction_active:store.rollback_transaction()
            vm.close()
            raise
        finally:
            if token is not None:_constructing.reset(token)
    # Actual record data wins over initializer assignments on GetObject.
    if values is not None:obj.values=dict(values)
    obj.revision=revision
    return obj


def write_object(caller,obj):
    app,store=obj.authorize(caller)
    if not obj._ready or _active_write.get():
        raise ValueError('recursive or initializing catalog write unsupported')
    owned=not store.transaction_active
    previous_revision=obj.revision
    token=None
    from .database_transactions import admission
    from .source_catalog_store import _HANDLED_CATALOG_WRITE
    try:
        if owned:store.begin_transaction()
        token=_active_write.set(True)
        with admission(False):
            yield from obj.event(caller,('beforewrite','передзаписью'))
            if not store.transaction_active:
                raise ValueError('catalog write transaction aborted by handler')
            obj.authorize(caller)
            obj.revision=store.write_record(obj.manager.name,obj.identity,obj.revision,obj.values,
                                            _handled=_HANDLED_CATALOG_WRITE)
            yield from obj.event(caller,('onwrite','призаписи'))
            if not store.transaction_active:
                raise ValueError('catalog write transaction aborted by handler')
            obj.authorize(caller)
        if owned:store.commit_transaction()
    except BaseException:
        if store.transaction_active:store.rollback_transaction()
        obj.revision=previous_revision
        raise
    finally:
        if token is not None:_active_write.reset(token)
