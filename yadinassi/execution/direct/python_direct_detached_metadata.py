"""Detached source metadata is a finite read-only capability, never a DB grant."""
from weakref import WeakKeyDictionary,ref
from decimal import Decimal
from uuid import UUID
from yadinassi.configuration import configuration_source_metadata as source
from yadinassi.configuration.metadata import _DeclaredMetadataCollection,MetadataObjectCollection
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_ROOT=source.SourceMetadataRoot;_OBJECT=source.SourceMetadataObject;_COLLECTION=_DeclaredMetadataCollection
_BINDINGS=source._DIRECT_DETACHED_METADATA_BINDINGS
_CLASSES=source._DIRECT_DETACHED_METADATA_CLASSES
_PARSER=source._DIRECT_DETACHED_METADATA_PARSER
_TABLES=source._DIRECT_DETACHED_METADATA_TABLES
_ORIGINS=source._DIRECT_DETACHED_METADATA_ORIGINS
_ADMISSION=source._detached_source_admission
_ADMISSION_BINDINGS=source._DIRECT_DETACHED_METADATA_ADMISSION_BINDINGS
_ADMISSION_CLASSES=source._DIRECT_DETACHED_METADATA_ADMISSION_CLASSES
_ADMISSION_MODULES=source._DIRECT_DETACHED_METADATA_ADMISSION_MODULES
_STATES=WeakKeyDictionary();_ROOTS=WeakKeyDictionary()
class _Seal:
    def __init__(self):self.fingerprint=None;self.keepalive=()

_METHODS={'count':(MetadataObjectCollection.count,0),'количество':(MetadataObjectCollection.count,0),
          'get':(MetadataObjectCollection.get,1),'получить':(MetadataObjectCollection.get,1),
          'find':(MetadataObjectCollection.find,1),'найти':(MetadataObjectCollection.find,1)}


def _owns(value):
    kind=type(value)
    return kind is _ROOT or kind is _OBJECT or kind is _COLLECTION


def _hooks():
    for module,name,value in source._DIRECT_DETACHED_METADATA_NAMESPACES:
        if vars(module).get(name) is not value:raise BoundaryViolation("detached metadata namespace constant changed")
    for name,value in source._DIRECT_DETACHED_METADATA_COLLECTION_GLOBALS:
        if vars(source._detached_metadata_module).get(name) is not value:raise BoundaryViolation('detached collection global changed')
    owners,original=source._DIRECT_DETACHED_METADATA_FILE_OWNERS
    if (source._FILE_OWNERS is not owners or type(owners) is not set or any(type(name) is not str for name in owners)
            or owners!=original):raise BoundaryViolation('detached metadata file family grants changed')
    for name,value in _ADMISSION_BINDINGS:
        if vars(_ADMISSION).get(name) is not value:raise BoundaryViolation('detached source admission hook changed')
    for cls,mro,fields in _ADMISSION_CLASSES:
        if cls.__mro__ is not mro or len(vars(cls))!=len(fields) or any(vars(cls).get(k) is not v for k,v in fields):
            raise BoundaryViolation('detached source admission class changed')
    if (_ADMISSION.ET is not _ADMISSION_MODULES[0] or _ADMISSION.io is not _ADMISSION_MODULES[1]
            or _ADMISSION.ET.iterparse is not _ADMISSION_MODULES[2] or _ADMISSION.io.StringIO is not _ADMISSION_MODULES[3]):
        raise BoundaryViolation('detached source admission parser changed')
    for name,maximum in _ADMISSION._DIRECT_SOURCE_XDTO_LIMITS:
        limit=getattr(_ADMISSION,name)
        if type(limit) is not int or not 0<limit<=maximum:raise BoundaryViolation('detached source admission quota changed')
    for name,value in _BINDINGS:
        if vars(source).get(name) is not value:raise BoundaryViolation('detached metadata binding changed')
    for cls,mro,fields in _CLASSES:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(name) is not value for name,value in fields):
            raise BoundaryViolation('detached metadata class hooks changed')
    if source.ET is not _PARSER[0] or source.ET.iterparse is not _PARSER[1] or source.BytesIO is not _PARSER[2]:
        raise BoundaryViolation('detached metadata parser changed')
    for name,value in source._DIRECT_DETACHED_METADATA_XML_FACTORIES:
        if vars(_PARSER[0]).get(name) is not value:raise BoundaryViolation('detached metadata XML factory changed')
    for cls,mro,fields in source._DIRECT_DETACHED_METADATA_XML_CLASSES:
        current=vars(cls)
        if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(name) is not value for name,value in fields):
            raise BoundaryViolation('detached metadata XML class changed')
    for name,value,entries in _TABLES:
        if vars(source).get(name) is not value:raise BoundaryViolation('detached metadata family table changed')
        if type(value) is dict:_dict(value)
        if type(value) is dict and (len(value)!=len(entries) or any(value.get(k) is not v for k,v in entries)):
            raise BoundaryViolation('detached metadata family mapping changed')


def _dict(value):
    if type(value) is not dict or len(value)>200000 or any(type(key) is not str for key in value):
        raise BoundaryViolation('detached metadata mapping changed')
    return value


def _origin(root):
    if type(root) is not _ROOT or type(vars(root)) is not dict:raise BoundaryViolation('detached metadata root changed')
    _dict(vars(root))
    original=_ORIGINS.get(root)
    if original is None:raise BoundaryViolation('detached metadata requires a constructed root')
    files,entries,inventory,items,fields,entry,name=original
    if root._files is not files or root._inventory is not inventory or root._entry is not entry or root._name is not name:
        raise BoundaryViolation('detached metadata origin replaced')
    _dict(files);_dict(inventory)
    if len(files)!=len(entries) or any(files.get(k) is not v or type(v) is not bytes for k,v in entries):
        raise BoundaryViolation('detached metadata source files changed')
    if len(inventory)!=len(items) or any(inventory.get(k) is not v for k,v in items):raise BoundaryViolation('detached metadata inventory changed')
    for item,saved,uuid_int in fields:
        if type(item) is not source.SourceMetadata:raise BoundaryViolation('detached metadata entry changed')
        if hasattr(item,'__dict__'):_dict(vars(item))
        if any(getattr(item,k) is not v for k,v in saved):raise BoundaryViolation('detached metadata fields changed')
        if type(item.identity) is not UUID or any(type(getattr(item,k)) is not str for k in ('family','name','path')):
            raise BoundaryViolation('detached metadata fields are not canonical')
        number=item.identity.int
        if type(number) is not int or not 0<=number<2**128 or type(uuid_int) is not int or number!=uuid_int:
            raise BoundaryViolation('detached metadata UUID changed')


def _graph(root):
    """Fingerprint links and XML; root-owned keepalive prevents identity reuse."""
    _origin(root);objects=_dict(root._objects);pending=[root];seen=set();fingerprint=[];receivers=[];keepalive=[root,objects];budget=200000
    for path,obj in objects.items():
        if type(obj) is not _OBJECT:raise BoundaryViolation('detached metadata object registry changed')
        _dict(vars(obj))
        if obj._entry is not root._inventory.get(path):
            raise BoundaryViolation('detached metadata object registry changed')
        pending.append(obj)
    while pending:
        obj=pending.pop()
        if id(obj) in seen:continue
        seen.add(id(obj));keepalive.append(obj);budget-=1
        if budget<0:raise BoundaryViolation('detached metadata graph limit')
        if type(obj) is _ROOT or type(obj) is _OBJECT:
            _dict(vars(obj))
            if obj._root is not root:raise BoundaryViolation('detached metadata object owner changed')
            expected={'_root','_entry','_parent','_name','_xml','_collections'}
            if obj is root:expected|={'_files','_inventory','_objects','_direct_detached_seal'}
            if obj._xml is not None:expected.add('_namespaces')
            if set(vars(obj))!=expected:raise BoundaryViolation('detached metadata instance hooks changed')
            keepalive.append(vars(obj))
            entry=obj._entry
            if (type(entry) is not source.SourceMetadata
                    or any(type(getattr(entry,key)) is not str for key in ('path','name','family'))
                    or root._inventory.get(entry.path) is not entry or obj._name is not entry.name):
                raise BoundaryViolation('detached metadata object provenance changed')
            if obj is root:
                if obj._parent is not None:raise BoundaryViolation('detached metadata root parent changed')
            elif root._objects.get(entry.path) is not obj:raise BoundaryViolation('detached metadata object is not registered')
            if obj._parent is not None:
                if type(obj._parent) is not _OBJECT:raise BoundaryViolation('detached metadata parent changed')
                _dict(vars(obj._parent))
                if obj._parent._root is not root:raise BoundaryViolation('detached metadata parent changed')
                pending.append(obj._parent)
            collections=_dict(obj._collections);keepalive.append(collections)
            for family,collection in collections.items():
                if family not in {v[0] for v in source._FAMILIES+source._FILE_CHILDREN} or type(collection) is not _COLLECTION:
                    raise BoundaryViolation('detached embedded metadata not integrated')
                pending.append(collection)
            fingerprint.append(('object',id(obj),tuple((k,id(v)) for k,v in vars(obj).items()),tuple((k,id(v)) for k,v in collections.items())))
            if obj._xml is not None:
                tree=[obj._xml]
                while tree:
                    element=tree.pop();keepalive.append(element);budget-=1
                    if budget<0 or type(element) is not source.ET.Element:raise BoundaryViolation('detached metadata XML graph changed')
                    if type(element.tag) is not str or (element.text is not None and type(element.text) is not str) or (element.tail is not None and type(element.tail) is not str):raise BoundaryViolation('detached metadata XML scalar changed')
                    attrs=_dict(element.attrib);keepalive.append(attrs)
                    if any(type(v) is not str for v in attrs.values()):raise BoundaryViolation('detached metadata XML attributes changed')
                    children=tuple(element);fingerprint.append(('xml',id(element),element.tag,element.text,element.tail,tuple(attrs.items()),tuple(id(c) for c in children)))
                    tree.extend(children)
                namespaces=getattr(obj,'_namespaces',None)
                if type(namespaces) is not dict:raise BoundaryViolation('detached metadata namespace cache changed')
                keepalive.append(namespaces)
                for element,scope in namespaces.items():
                    keepalive.extend((element,scope))
                    if type(element) is not source.ET.Element:raise BoundaryViolation('detached metadata namespace key changed')
                    _dict(scope)
                    if any(type(v) is not str for v in scope.values()):raise BoundaryViolation('detached metadata namespace value changed')
                    fingerprint.append(('namespace',id(element),tuple(scope.items())))
        elif type(obj) is _COLLECTION:
            _dict(vars(obj))
            if set(vars(obj))!={'_items'}:raise BoundaryViolation('detached metadata collection fields changed')
            items=_dict(obj._items);keepalive.extend((vars(obj),items))
            for key,item in items.items():
                if type(item) is not _OBJECT:raise BoundaryViolation('detached metadata collection item changed')
                _dict(vars(item))
                if type(item._name) is not str or key!=item._name.casefold():raise BoundaryViolation('detached metadata collection item changed')
                pending.append(item)
            fingerprint.append(('collection',id(obj),id(items),tuple((k,id(v)) for k,v in items.items())))
        else:raise BoundaryViolation('detached metadata receiver changed')
        receivers.append(obj)
    return tuple(fingerprint),receivers,tuple(keepalive)


def _check(boundary,value):
    boundary._check()
    if not getattr(boundary,'_detached_metadata_active',False):raise BoundaryViolation('detached metadata boundary expired')
    _hooks()
    root=value if type(value) is _ROOT else (_ROOTS.get(value)() if value in _ROOTS else None)
    if root is None:raise BoundaryViolation('detached metadata receiver has no admitted root')
    _origin(root);_dict(root._objects);_dict(root._collections)
    saved=_STATES.get(root)
    seal=None if saved is None else saved()
    if seal is None:
        if (value is not root or root._xml is not None or root._objects or root._collections
                or '_namespaces' in vars(root) or '_direct_detached_seal' in vars(root)):
            raise BoundaryViolation('detached metadata requires pristine initial root')
        _origin(root)
        canonical=_ADMISSION.import_source(root._files)
        if len(canonical.metadata)!=len(root._inventory):raise BoundaryViolation('detached metadata manufactured inventory')
        for item in canonical.metadata:
            old=root._inventory.get(item.path)
            if (old is None or old.identity.int!=item.identity.int or old.family!=item.family
                    or old.name!=item.name or old.path!=item.path):
                raise BoundaryViolation('detached metadata source inventory mismatch')
        seal=_Seal();root._direct_detached_seal=seal;_STATES[root]=ref(seal)
        fingerprint,receivers,keepalive=_graph(root)
        seal.fingerprint=fingerprint;seal.keepalive=keepalive
    else:
        if getattr(root,'_direct_detached_seal',None) is not seal:raise BoundaryViolation('detached metadata seal changed')
        fingerprint,receivers,_=_graph(root)
        if fingerprint!=seal.fingerprint:raise BoundaryViolation('detached metadata cached graph changed')
    if not any(obj is value for obj in receivers):raise BoundaryViolation('detached metadata receiver revoked')
    return root


def _lookup(boundary,value,operation):
    root=_check(boundary,value)
    try:result=operation()
    finally:
        # Only guarded canonical operations may expand the lazy cache. Failed
        # lookups can still parse XML or cache validated preceding children.
        _hooks();_origin(root)
        fingerprint,receivers,keepalive=_graph(root)
        seal=_STATES[root]()
        if seal is None or root._direct_detached_seal is not seal:raise BoundaryViolation('detached metadata seal changed')
        seal.fingerprint=fingerprint;seal.keepalive=keepalive
        for item in receivers:_ROOTS[item]=ref(root)
        boundary._check()
    if _owns(result) and not any(result is item for item in receivers):raise BoundaryViolation('detached metadata lookup escaped its root')
    return result


class DetachedMetadataBoundary:
    def enter(self):
        super().enter();self._detached_metadata_epoch=object();self._detached_metadata_active=True
    def leave(self):
        self._detached_metadata_active=False;return super().leave()
    def get_member(self,value,name):
        if not _owns(value):return super().get_member(value,name)
        _check(self,value)
        if type(value) is _COLLECTION:
            return _lookup(self,value,lambda:MetadataObjectCollection.get_member(value,name))
        key=name.casefold()
        if key in ('name','имя'):return value._name
        family=source._COLLECTIONS.get(key)
        if family is None or family not in source._FAMILIES+source._FILE_CHILDREN:
            raise ValueError('detached metadata member not integrated')
        return _lookup(self,value,lambda:_OBJECT._collection(value,family))
    def resolve_set_member(self,value,name):
        if _owns(value):_check(self,value);raise ValueError('detached metadata is read-only')
        return super().resolve_set_member(value,name)
    def resolve_member_call(self,value,name,*,require_value=False,omitted=()):
        if not _owns(value):return super().resolve_member_call(value,name,require_value=require_value,omitted=omitted)
        if omitted:raise TypeError('detached metadata does not accept omissions')
        return self.resolve_member(value,name)
    def resolve_member(self,value,name):
        if not _owns(value):return super().resolve_member(value,name)
        _check(self,value)
        if type(value) is not _COLLECTION:raise ValueError('detached metadata method not integrated')
        key=name.casefold()
        epoch=self._detached_metadata_epoch
        def current():
            _check(self,value)
            if self._detached_metadata_epoch is not epoch:raise BoundaryViolation('detached metadata callback expired')
        if name=='__iter__':
            def iterator():
                current()
                for item in tuple(value._items.values()):
                    current();yield item
            return iterator
        if name=='__getitem__':method,count=MetadataObjectCollection.get_index,1
        elif key in _METHODS:method,count=_METHODS[key]
        else:raise ValueError('detached metadata method not integrated')
        def call(*args):
            current()
            if len(args)!=count:raise TypeError('invalid detached metadata method arity')
            return _lookup(self,value,lambda:method(value,*args))
        return call
