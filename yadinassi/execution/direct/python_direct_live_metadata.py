"""Read-only live metadata protocol over one current interpreter/database root."""
from types import MethodType,FunctionType
from uuid import UUID
from yadinassi.configuration import metadata as native
from yadinassi.types import type_descriptions, type_qualifiers
from yadinassi.db.catalog import catalog_types
from yadinassi.db.document import document_types
from yadinassi.db.registers import information_registers
from yadinassi.db.catalog.catalogs import BSLCatalogs,BSLCatalogManager,_DIRECT_MOVEMENT_PARENT_CLASSES as _CATALOG_ABI
from yadinassi.db.document.documents import BSLDocuments,BSLDocumentManager,_DIRECT_MOVEMENT_PARENT_CLASSES as _DOCUMENT_ABI
from yadinassi.execution.codegen.direct_live_state import _ForwardReference
from yadinassi.types.values import Reference
from yadinassi.db.catalog.catalog_backend import _DIRECT_LIVE_METADATA_SCHEMA_ABI as _SCHEMA1
from yadinassi.db.document.document_backend import _DIRECT_LIVE_METADATA_SCHEMA_ABI as _SCHEMA2
from yadinassi.db.registers.register_backend import _DIRECT_LIVE_METADATA_SCHEMA_ABI as _SCHEMA3
from yadinassi.execution.codegen.direct_boundaries import BoundaryViolation
from yadinassi.db.database_context import SQLiteDBContext,_DIRECT_MOVEMENT_PARENT_CLASSES as _CONTEXT_ABI
from yadinassi.db.sqlite.sqlite_catalog import SQLiteCatalogBackend,_DIRECT_MOVEMENT_PARENT_CLASSES as _BACKEND_ABI
from yadinassi.types.values import HostFunction,_DIRECT_COLLECTION_CLASS_ABI

_TYPES=(native.BSLMetadata,native.BSLCatalogMetadataCollection,native.BSLDocumentMetadataCollection,
        native.BSLInformationRegisterMetadataCollection,native.BSLCatalogMetadata,native.BSLDocumentMetadata,
        native.BSLInformationRegisterMetadata,native.BSLAttributeMetadata,native.BSLTabularSectionMetadata,
        native._DeclaredMetadataCollection,native.StandardAttributeDescriptions,native.StandardAttributeDescription)
TYPE_IDS=frozenset(map(id,_TYPES))
_ORIGINS=native._LIVE_METADATA_ORIGINS
_COLLECTIONS=(native.BSLCatalogMetadataCollection,native.BSLDocumentMetadataCollection,
              native.BSLInformationRegisterMetadataCollection,native._DeclaredMetadataCollection,native.StandardAttributeDescriptions)

def _class_hooks(records):
    for cls,mro,fields in records:
        now=vars(cls)
        if cls.__mro__ is not mro or len(now)!=len(fields) or any(now.get(k) is not v for k,v in fields):
            raise BoundaryViolation('live metadata class protocol changed')

def _hooks():
    _class_hooks(native._DIRECT_LIVE_METADATA_CLASSES+_CONTEXT_ABI+_BACKEND_ABI+(_DIRECT_COLLECTION_CLASS_ABI[-1],))
    _class_hooks(_CATALOG_ABI+_DOCUMENT_ABI+_SCHEMA1+_SCHEMA2+_SCHEMA3+native._DIRECT_LIVE_METADATA_UUID_ABI+_DIRECT_COLLECTION_CLASS_ABI)
    for module,name in ((catalog_types,'BSLCatalogType'),(document_types,'BSLDocumentType'),(information_registers,'BSLInformationRegisterType')):
        if vars(module).get(name) is not module._DIRECT_LIVE_METADATA_TYPE:raise BoundaryViolation('live metadata type binding changed')
        _class_hooks(module._DIRECT_LIVE_METADATA_TYPE_ABI)
    for module in (native,type_descriptions,type_qualifiers):
        _class_hooks(module._DIRECT_LIVE_METADATA_CLASSES)
        for name,value in module._DIRECT_LIVE_METADATA_BINDINGS:
            if vars(module).get(name) is not value:raise BoundaryViolation('live metadata helper changed')

def _fields(value):
    fields=vars(value)
    if type(fields) is not dict or any(type(key) is not str for key in fields):raise BoundaryViolation('live metadata fields changed')
    for cls in type(value).__mro__:
        for name,member in vars(cls).items():
            if any(type(member) is kind for kind in (FunctionType,property,staticmethod,classmethod)) and name in fields:
                rebound=fields[name]
                if type(member) is FunctionType and type(rebound) is MethodType and rebound.__self__ is value and rebound.__func__ is member:continue
                raise BoundaryViolation('live metadata instance helper shadowed')
    return fields

def registered(value):
    if id(type(value)) not in TYPE_IDS:return False
    _hooks()
    return value in _ORIGINS

def _matches(value,frozen):
    tag,saved=frozen
    if tag=='uuid':return value is saved[0] and type(value.int) is int and value.int==saved[1]
    if tag=='schema':return value is saved[0] and all(_matches(getattr(value,name),record) for name,record in saved[1])
    if tag=='weak':return saved() is value
    if tag=='value':return saved is value
    if tag=='tuple':return type(value) is tuple and len(value)==len(saved) and all(_matches(v,s) for v,s in zip(value,saved))
    if type(value) is not dict or any(type(k) is not str for k in value):return False
    return len(value)==len(saved) and all(k in value and _matches(value[k],v) for k,v in saved)

def _node(value):
    if not registered(value):raise BoundaryViolation('unissued live metadata receiver')
    fields=_fields(value);parent,relation,snapshot=_ORIGINS[value]
    expected={name for name,_ in snapshot}
    if type(value) is not native.BSLMetadata and fields.keys()!=expected:
        raise BoundaryViolation('live metadata instance protocol changed')
    if any(name not in fields or not _matches(fields[name],record) for name,record in snapshot):
        raise BoundaryViolation('live metadata provenance changed')
    return None if parent is None else parent(),relation

def _without_database(vm,root,value):
    # Only the issued root and its unloaded shells exist. The metadata model
    # itself signals db required when a lookup actually needs storage.
    if (root._identity is not None or root._configuration_name is not None
            or root._common_modules is not None or root._common_templates is not None
            or root._enumerations is not None or root._session_parameters is not None):
        raise BoundaryViolation('metadata without a database must be unconfigured')
    catalogs=vm._catalogs
    if type(catalogs) is not BSLCatalogs:
        raise BoundaryViolation('live metadata manager binding changed')
    _fields(catalogs)
    if catalogs._metadata is not root._catalogs or catalogs._context is not None:
        raise BoundaryViolation('foreign live metadata root')
    shells=(root._catalogs,root._documents,root._information_registers)
    if value is not root and not any(value is shell for shell in shells):
        raise BoundaryViolation('foreign live metadata receiver')
    for shell in shells:
        _node(shell)
        if shell._context is not None or shell._root is not root or shell._items is not None:
            raise BoundaryViolation('foreign live metadata family')
    return root


def check(boundary,value):
    boundary._check();_hooks()
    if not boundary._live_metadata_active:raise BoundaryViolation('live metadata activation ended')
    root=boundary.vm._metadata
    if type(root) is not native.BSLMetadata:raise BoundaryViolation('live metadata root changed')
    _node(root)
    context=boundary.vm.database_context
    if context is None:return _without_database(boundary.vm,root,value)
    if type(context) is not SQLiteDBContext:raise BoundaryViolation('live metadata context required')
    _fields(context);backend=context._backend
    if type(backend) is not SQLiteCatalogBackend:raise BoundaryViolation('live metadata backend changed')
    _fields(backend)
    if backend._closed is not False:raise BoundaryViolation('live metadata database closed')
    for collection in (root._catalogs,root._documents,root._information_registers):
        _node(collection)
        if collection._context is not context or collection._root is not root:raise BoundaryViolation('foreign live metadata family')
    if type(root._catalog_managers) is not BSLCatalogs or type(root._document_managers) is not BSLDocuments:raise BoundaryViolation('live metadata manager family changed')
    _fields(root._catalog_managers);_fields(root._document_managers)
    vm=boundary.vm
    family=vm._family_owner
    local_catalogs,local_documents=vm._catalogs,vm._documents
    if vm is family:
        if root._catalog_managers is not local_catalogs or root._document_managers is not local_documents:
            raise BoundaryViolation('live metadata manager binding changed')
    else:
        # Same-family imports own distinct executable manager wrappers.
        # Reference types are decoded using the graph's pinned managers.
        if (vm._family_released or family._family_closed
                or vm._family_generation!=family._family_generation
                or family._schema_scopes.get(id(context)) is not root
                or type(local_catalogs) is not BSLCatalogs or type(local_documents) is not BSLDocuments):
            raise BoundaryViolation('live metadata manager binding changed')
        _fields(local_catalogs);_fields(local_documents)
        if (local_catalogs._metadata is not root._catalogs or local_catalogs._context is not context
                or local_documents._metadata is not root._documents or local_documents._context is not context
                or local_documents._catalogs is not local_catalogs or local_documents._interpreter is not vm):
            raise BoundaryViolation('live metadata manager binding changed')
    catalogs=root._catalog_managers;documents=root._document_managers
    if (catalogs._metadata is not root._catalogs or catalogs._context is not context
            or documents._metadata is not root._documents or documents._context is not context
            or documents._catalogs is not catalogs):raise BoundaryViolation('live metadata manager snapshot changed')
    for collection,kind in ((catalogs,BSLCatalogManager),(documents,BSLDocumentManager)):
        managers=collection._managers
        if type(managers) is not dict or any(type(k) is not str for k in managers):raise BoundaryViolation('live metadata manager registry changed')
        for manager in managers.values():
            if type(manager) is not kind:raise BoundaryViolation('live metadata cached manager changed')
            _fields(manager);_node(manager._metadata)
            if manager._catalogs is not catalogs:raise BoundaryViolation('foreign live metadata manager')
            if kind is BSLDocumentManager and manager._documents is not documents:raise BoundaryViolation('foreign document metadata manager')
    identity=root._identity
    if identity is not None:
        if (type(identity) is not tuple or len(identity)!=2 or type(identity[0]) is not UUID
                or type(backend.database_id) is not UUID or type(identity[0].int) is not int or type(backend.database_id.int) is not int
                or type(identity[1]) is not int or type(backend.configuration_generation) is not int
                or identity[0].int!=backend.database_id.int or identity[1]!=backend.configuration_generation):
            raise BoundaryViolation('live metadata database generation changed')
    seen=set();current=value
    while current is not root:
        if id(current) in seen or len(seen)>12:raise BoundaryViolation('live metadata ownership cycle')
        seen.add(id(current));parent,relation=_node(current)
        if parent is None:raise BoundaryViolation('foreign live metadata root')
        _node(parent);kind,key=relation
        if kind=='field':linked=vars(parent).get(key)
        elif kind=='child':linked=parent._children.get(key)
        elif kind=='item':linked=parent._items.get(key)
        elif kind=='standard':linked=parent._items[key] if key<len(parent._items) else None
        else:raise BoundaryViolation('live metadata relation changed')
        if linked is not current:raise BoundaryViolation('live metadata receiver detached')
        current=parent
    return root

def _type_argument(value):
    kinds=(catalog_types._DIRECT_LIVE_METADATA_TYPE,document_types._DIRECT_LIVE_METADATA_TYPE,information_registers._DIRECT_LIVE_METADATA_TYPE)
    if not any(type(value) is cls for cls in kinds):return
    fields=_fields(value)
    if fields:raise BoundaryViolation('live metadata type instance fields changed')
    if type(value.name) is not str or type(value.family) is not str:raise BoundaryViolation('live metadata type shape changed')
    identity=value.metadata_uuid
    if type(identity) is not UUID or type(identity.int) is not int or not 0<=identity.int<2**128:
        raise BoundaryViolation('live metadata type identity changed')

def _owned(boundary,value):
    if id(type(value)) in TYPE_IDS:check(boundary,value)
    return value

def _read(boundary,value,name):
    check(boundary,value)
    result=value.get_member(name)
    check(boundary,value)
    if type(result) is HostFunction:
        return result
    return _owned(boundary,result)

def _bind(boundary,value,name):
    check(boundary,value);epoch=boundary._live_metadata_epoch
    def current():
        check(boundary,value)
        if boundary._live_metadata_epoch is not epoch:raise BoundaryViolation('live metadata callback expired')
    if name=='__iter__':
        if not any(type(value) is cls for cls in _COLLECTIONS):raise ValueError('metadata object is not iterable')
        def iterate():
            current();items=tuple(value);current()
            for item in items:current();yield _owned(boundary,item)
        return iterate
    if name=='__setitem__':
        def readonly(index,new):
            current();raise ValueError('metadata is read-only')
        return readonly
    if name=='__getitem__':method=value.get_index
    else:
        function=value.get_method(name)
        if type(function) is not HostFunction:raise BoundaryViolation('metadata method changed')
        method=function.function
    def call(*args):
        current()
        if type(value) is native.BSLMetadata and name.casefold() in ('findbytype','найтипотипу') and args:_type_argument(args[0])
        result=method(*args)
        current();return _owned(boundary,result)
    return call


def server_receiver(boundary):
    from .python_direct_server import ServerBoundary, _LOGICAL_METADATA
    return (type(boundary) is ServerBoundary and boundary._server_side
            and boundary._logical_metadata is _LOGICAL_METADATA)

def get(boundary,value,name):
    result=_read(boundary,value,name)
    if type(result) is not HostFunction:return result
    # Capture the verified operation, not its underlying Python method. The
    # generic captured-value lane is already restricted to actual captures.
    from .python_direct_captured_values import register
    return register(HostFunction(name,_bind(boundary,value,name)))

def resolve(boundary,value,name,*,syntax=False,require_value=False,omitted=()):
    if omitted:raise TypeError('metadata methods do not accept omissions')
    if not syntax and name.startswith('_'):
        raise ValueError('Метод объекта не обнаружен: '+name)
    return _bind(boundary,value,name)

class LiveMetadataBoundary:
    def enter(self):
        super().enter();self._live_metadata_epoch=object();self._live_metadata_active=True
    def leave(self):
        self._live_metadata_active=False;return super().leave()
    def get_member(self,value,name):
        if not registered(value):return super().get_member(value,name)
        return _read(self,value,name)
    def resolve_set_member(self,value,name):
        if not registered(value):return super().resolve_set_member(value,name)
        check(self,value);epoch=self._live_metadata_epoch
        def readonly(new):
            check(self,value)
            if self._live_metadata_epoch is not epoch:raise BoundaryViolation('live metadata callback expired')
            raise ValueError('metadata is read-only')
        return readonly
    def reference_member(self,value,name):
        if not registered(value):return super().reference_member(value,name)
        self.get_member(value,name)
        epoch=self._live_metadata_epoch
        def read():
            if self._live_metadata_epoch is not epoch:raise BoundaryViolation('live metadata reference expired')
            return self.get_member(value,name)
        def write(new):
            read();self.resolve_set_member(value,name)(new)
        return _ForwardReference(Reference(read,write))
    def reference_index(self,value,index):
        if not registered(value):return super().reference_index(value,index)
        self.resolve_member(value,'__getitem__')(index)
        epoch=self._live_metadata_epoch
        def read():
            if self._live_metadata_epoch is not epoch:raise BoundaryViolation('live metadata reference expired')
            return self.resolve_member(value,'__getitem__')(index)
        def write(new):
            read();self.resolve_member(value,'__setitem__')(index,new)
        return _ForwardReference(Reference(read,write))
    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if not registered(value):return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        if omitted:raise TypeError('metadata methods do not accept omissions')
        return self.resolve_member(value,name)
    def resolve_member(self,value,name):
        if not registered(value):return super().resolve_member(value,name)
        return _bind(self,value,name)
    def resolve_callable(self,value,*,require_value=False,allow_references=False,_extension_value=False):
        if type(value) is HostFunction:
            _class_hooks((_DIRECT_COLLECTION_CLASS_ABI[-1],));_fields(value)
            callback=value.function
            if type(callback) is MethodType and registered(callback.__self__):
                receiver=callback.__self__;check(self,receiver)
                public=('full_name','find_by_type','find_by_full_name','count','get','find','index_of','contains')
                if not any(callback.__func__ is vars(cls).get(name) for cls in type(receiver).__mro__ for name in public):
                    raise BoundaryViolation('live metadata saved method changed')
                epoch=self._live_metadata_epoch;label=value.name
                def current():
                    check(self,receiver);_fields(value)
                    if (self._live_metadata_epoch is not epoch or value.function is not callback or type(value.name) is not str
                            or value.name is not label or value.returns_value is not True
                            or type(value.reference_parameters) is not frozenset or value.reference_parameters):
                        raise BoundaryViolation('live metadata saved method expired')
                current()
                def call(*args):
                    current()
                    if callback.__func__ is native.BSLMetadata.find_by_type and args:_type_argument(args[0])
                    result=callback(*args);check(self,receiver);return _owned(self,result)
                if allow_references:call.requires_reference=lambda index:False
                return call
        return super().resolve_callable(value,require_value=require_value,allow_references=allow_references,_extension_value=_extension_value)
