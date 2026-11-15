"""Explicit nonposting document objects with bounded modules and real stored data."""
from uuid import UUID, uuid4
from contextvars import ContextVar
from .syntax import ast
from .configuration_source_runtime import _SourceInterpreter

_constructing=ContextVar("source_document_construction",default=())
_active_write=ContextVar("source_document_write",default=False)
from .values import BSLObject, HostFunction
from .source_references import SourceReferenceManager
from .source_constant_store import _encode

_ALIASES={'номер':'number','дата':'date','пометкаудаления':'deletionmark','проведен':'posted','ссылка':'ref'}
_OBJECT_METHODS={'read':'read','прочитать':'read','write':'write','записать':'write','isnew':'new','этоновый':'new','metadata':'metadata','метаданные':'metadata'}
_MANAGER_METHODS={'createdocument':'create','создатьдокумент':'create','select':'select','выбрать':'select'}


def store_for(manager,caller):
    from .safe_mode import require_external_access
    from .source_document_store import SourceDocumentStore
    from .source_document_section_store import SourceDocumentSectionStore
    from .source_catalog_runtime import _constructing as catalog_construction, _active_write as catalog_write
    from .source_constant_managers import _active_write as constant_write, _constructing as constant_construction
    app=manager.authorize(caller)
    if caller._scheduler.pending:raise ValueError('source document operations require no pending asynchronous tasks')
    require_external_access('source document database')
    if manager.family!='Document' or type(app.constant_store) not in (SourceDocumentStore,SourceDocumentSectionStore):
        raise ValueError('source Document records require explicit v5 scratch capability')
    app.constant_store.document(manager.name)
    if (_constructing.get() or _active_write.get() or catalog_construction.get() or catalog_write.get() or constant_write.get() or constant_construction.get()) and not app.constant_store.transaction_active:
        raise ValueError('source lifecycle transaction aborted; document access refused')
    return app,app.constant_store


class SourceDocumentObject(BSLObject):
    def __init__(self,manager,definition,identity=None,revision=0,values=None):
        self.manager,self.definition=manager,definition
        self.identity=identity or uuid4();self.revision=revision
        self.values=dict(values) if values is not None else {'number':'','deletionmark':False,'posted':False}
        self.fields={f.name.casefold():f for f in definition.fields}
        self.interpreter=None;self._ready=True;self._closed=False
        self.sections={}
        self.replace_sections({s.name.casefold():() for s in definition.sections})

    def replace_sections(self,values):
        from .source_document_sections import SourceDocumentSection
        new={s.name.casefold():SourceDocumentSection(self,s,values[s.name.casefold()]) for s in self.definition.sections}
        for section in self.sections.values():section.invalidate()
        self.sections=new


    def authorize(self,caller):
        app,store=store_for(self.manager,caller)
        if self._closed or (not self._ready and caller is not self.interpreter):raise ValueError('document initialization incomplete or failed')
        if self.interpreter is not None:self.interpreter._require_family()
        return app,store

    def exported_routine(self,caller,name):
        self.authorize(caller)
        if self.interpreter is None:raise ValueError('document exported routine unavailable')
        return self.interpreter._self_module.routine(name)

    def event(self,caller):
        vm=self.interpreter
        if vm is None:return
        matches=[vm.server_routines[n] for n in ('onwrite','призаписи') if n in vm.server_routines]
        if not matches:return
        routine=matches[0];vm.variables['__document_cancel']=False
        try:
            yield from vm.call_routine(routine,[ast.Name(routine.token,'__document_cancel')],vm,require_value=False)
            cancel=vm.variables['__document_cancel']
            if type(cancel) is not bool:raise TypeError('document Cancel requires Boolean')
            if cancel:raise ValueError('document write cancelled by handler')
        finally:vm.variables.pop('__document_cancel',None)


    def property_read(self,caller,name):
        app,_=self.authorize(caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key in _OBJECT_METHODS:return self.get_member(name)
        if key=='ref':return app.references.ref('Document',self.manager.name,self.identity if self.revision else UUID(int=0))
        if key in self.sections:return self.sections[key]
        if key not in self.fields:
            if self.interpreter is not None:return self.interpreter._self_module.get_member(name)
            raise ValueError('unknown source document field: '+name)
        if key not in self.values:raise ValueError('source document field requires explicit assignment: '+name)
        return self.values[key]

    def property_write(self,caller,name,value):
        self.authorize(caller);key=_ALIASES.get(name.casefold(),name.casefold())
        if key not in self.fields or key=='posted':
            if self.interpreter is not None and key not in self.fields and key not in self.sections and key not in _OBJECT_METHODS and key not in ('ref','thisobject','этотобъект'):
                return self.interpreter._self_module.set_member(name,value)
            raise ValueError('source document field readonly or unknown: '+name)
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
        if self.operation=='create':return (yield from create_object(caller,manager,definition))
        if self.operation=='select':return SourceDocumentSelection(manager,store.read_documents(manager.name))
        if self.operation=='getobject':
            return (yield from load_object(caller,manager,definition,store,self.identity))
        if self.operation=='next':
            receiver.index+=1;return receiver.index<len(receiver.rows)
        if self.operation=='object':
            if 'onread' in definition.write_blockers:raise ValueError('document OnRead lifecycle unsupported')
            if not 0<=receiver.index<len(receiver.rows):raise ValueError('source selection is not positioned')
            identity,revision,fields=receiver.rows[receiver.index]
            if definition.sections:return (yield from load_object(caller,manager,definition,store,identity))
            return (yield from create_object(caller,manager,definition,identity,revision,fields))
        receiver.authorize(caller)
        if self.operation=='new':return receiver.revision==0
        if self.operation=='metadata':return app.references.definition('Document',manager.name)[2]
        if self.operation=='read':
            if 'onread' in definition.write_blockers:raise ValueError('document OnRead lifecycle unsupported')
            if definition.sections:
                _,revision,fields,sections=store.read_document_bundle(manager.name,receiver.identity)
                receiver.replace_sections(sections)
            else:_,revision,fields=store.read_documents(manager.name,receiver.identity)[0]
            receiver.values,receiver.revision=fields,revision;return None
        if self.operation=='write':
            yield from write_object(caller,receiver)
            return None
        raise ValueError('unsupported source document operation')


def load_object(caller,manager,definition,store,identity):
    if 'onread' in definition.write_blockers:raise ValueError('document OnRead lifecycle unsupported')
    if definition.sections:
        rid,revision,fields,sections=store.read_document_bundle(manager.name,identity)
        return (yield from create_object(caller,manager,definition,rid,revision,fields,sections))
    rid,revision,fields=store.read_documents(manager.name,identity)[0]
    return (yield from create_object(caller,manager,definition,rid,revision,fields))


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


class _ObjectInterpreter(_SourceInterpreter):
    def __init__(self,obj,app):
        super().__init__(app,family_owner=app.interpreter,compilation_profile=app.compilation_profile)
        self.object=obj
        self._logical_side='server'

    def field(self,name):
        key=_ALIASES.get(name.casefold(),name.casefold())
        return key in self.object.fields or key in self.object.sections or key=='ref'

    def visit_Name(self,node):
        if node.name.casefold() in ('thisobject','этотобъект'):return self.object
        if node.name.casefold() in _OBJECT_METHODS:return self.object.get_member(node.name)
        if self.field(node.name):return self.object.property_read(self,node.name)
        return super().visit_Name(node)

    def call(self,node,*,require_value):
        callee=self.ungroup(node.callee)
        # A field expression remains the value; a builtin call uses its callable.
        if (type(callee) is ast.Name and self.field(callee.name)
                and callee.name.casefold() in self.functions
                and self._resolve_routine(callee.name) is None):
            node=ast.Call(node.token,ast.Literal(node.token,self.functions[callee.name.casefold()]),node.arguments)
        return (yield from super().call(node,require_value=require_value))

    def set_variable(self,name,value):
        if name.casefold() in ('thisobject','этотобъект'):
            raise ValueError('ThisObject is read-only')
        if self.field(name):return self.object.property_write(self,name,value)
        return super().set_variable(name,value)

    def argument(self,node):
        node=self.ungroup(node)
        from .runtime import _Reference
        if type(node) is ast.Name and node.name.casefold()=='__document_cancel':
            return _Reference(lambda:self.variables['__document_cancel'],
                              lambda value:self.variables.__setitem__('__document_cancel',value))
        if type(node) is ast.Name and self.field(node.name):
            self.object.property_read(self,node.name)
            return _Reference(lambda:self.object.property_read(self,node.name),
                              lambda value:self.object.property_write(self,node.name,value))
        return (yield from super().argument(node))



def create_object(caller,manager,definition,identity=None,revision=0,values=None,sections=None):
    app,store=store_for(manager,caller)
    obj=SourceDocumentObject(manager,definition,identity)
    path=definition.object_module
    if path is not None:
        from .source_document_definitions import document_module_program
        program,blockers=document_module_program(app.files[path],path,definition.fields,definition.sections)
        if blockers!=definition.write_blockers:raise ValueError('document event binding mismatch')
        stack=_constructing.get();key=(id(app),definition.identity)
        if key in stack or len(stack)>=32:raise ValueError('recursive or excessive document initialization')
        vm=_ObjectInterpreter(obj,app);obj.interpreter=vm;obj._ready=False
        token=None;owned=not store.transaction_active
        from .database_transactions import admission
        from .safe_mode import routine_frame
        try:
            if owned:store.begin_transaction()
            token=_constructing.set((*stack,key));vm._self_module.ready=True
            with admission(False),routine_frame(caller,vm):yield from vm._execute_program(program)
            if not store.transaction_active:raise ValueError('document initialization transaction aborted')
            store_for(manager,caller)
            if owned:store.commit_transaction()
            obj._ready=True
        except BaseException:
            obj._closed=True
            for section in obj.sections.values():section.invalidate()
            if store.transaction_active:store.rollback_transaction()
            vm.close();raise
        finally:
            if token is not None:_constructing.reset(token)
    if values is not None:obj.values=dict(values)
    if sections is not None:obj.replace_sections(sections)
    obj.revision=revision
    return obj


def write_object(caller,obj):
    _,store=obj.authorize(caller)
    if obj.definition.write_blockers:
        raise ValueError('source document Write unsupported events: '+','.join(obj.definition.write_blockers))
    from .source_catalog_runtime import _active_write as catalog_write
    if not obj._ready or _active_write.get() or catalog_write.get():raise ValueError('recursive or initializing document write unsupported')
    owned=not store.transaction_active;previous_revision=obj.revision;token=None
    from .database_transactions import admission
    from .source_document_store import _HANDLED_DOCUMENT_WRITE
    try:
        if owned:store.begin_transaction()
        token=_active_write.set(True)
        with admission(False):
            obj.authorize(caller)
            if obj.definition.sections:
                sections={name:tuple(dict(row.values) for row in section.rows) for name,section in obj.sections.items()}
                obj.revision=store.write_document_bundle(obj.manager.name,obj.identity,obj.revision,obj.values,sections,_handled=_HANDLED_DOCUMENT_WRITE)
            else:obj.revision=store.write_document(obj.manager.name,obj.identity,obj.revision,obj.values,_handled=_HANDLED_DOCUMENT_WRITE)
            yield from obj.event(caller)
            if not store.transaction_active:raise ValueError('document write transaction aborted by handler')
            obj.authorize(caller)
        if owned:store.commit_transaction()
    except BaseException:
        if store.transaction_active:store.rollback_transaction()
        obj.revision=previous_revision;raise
    finally:
        if token is not None:_active_write.reset(token)
