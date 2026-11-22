"""Read-only source enumeration identities and their owned metadata tree."""
from uuid import UUID
from yadinassi.db.metadata.enumerations import BSLEnumerations,BSLEnumManager,EnumMetadata,EnumValueMetadata,_DIRECT_ENUM_ABI
from yadinassi.db.metadata.enum_types import BSLEnumReference,BSLEnumType
from yadinassi.configuration.metadata import _DeclaredMetadataCollection
from yadinassi.configuration.configuration_source_metadata import SourceMetadataRoot,SourceMetadataObject
from yadinassi.configuration.configuration_source import SourceMetadata
from yadinassi.configuration.configuration_enumerations import EnumDefinition
from yadinassi.types.values import HostFunction
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

_TYPES=(BSLEnumerations,BSLEnumManager,BSLEnumReference,EnumMetadata,EnumValueMetadata)
_ZERO={'count','количество','emptyref','пустаяссылка','metadata','метаданные','isempty','пустая','fullname','полноеимя'}
_ONE={'get','получить','indexof','индекс','find','найти','contains','содержит'}
FIND_BY_TYPE=('findbytype','найтипотипу')


def _abi(value):
    kind=type(value)
    for cls,methods in _DIRECT_ENUM_ABI:
        if kind is cls:
            try:local=object.__getattribute__(value,'__dict__')
            except AttributeError:local={}
            if any(name in local or getattr(cls,name) is not expected for name,expected in methods):
                raise BoundaryViolation('source enumeration hooks changed')
            return
    raise BoundaryViolation('noncanonical source enum receiver')


def _root(boundary):
    boundary._check();root=boundary.app.enumerations
    if (type(root) is not BSLEnumerations or type(root._managers) is not dict
            or type(root.metadata) is not _DeclaredMetadataCollection
            or type(root.metadata._items) is not dict
            or boundary.vm._metadata._enumerations is not root):
        raise BoundaryViolation('source enumeration namespace changed')
    _abi(root);_abi(root.metadata)
    if (any(type(key) is not str for key in root.metadata._items)
            or len(root.metadata._items)!=len(root._managers)):
        raise BoundaryViolation('source enum metadata mapping changed')
    return root


def _managers(root):
    for key,manager in root._managers.items():
        if (type(key) is not str or type(manager) is not BSLEnumManager
                or type(manager._metadata) is not EnumMetadata
                or root.metadata._items.get(key) is not manager._metadata
                or type(manager._value_type) is not BSLEnumType
                or manager._value_type.snapshot is not root.metadata):
            raise BoundaryViolation('source enumeration manager binding changed')
        _abi(manager);_abi(manager._metadata);_abi(manager._value_type)
        definition=manager._metadata._definition
        if (manager._value_type.family!='ref' or type(manager._value_type.metadata_uuid) is not UUID
                or manager._value_type.metadata_uuid!=definition.identity
                or type(manager._manager_type) is not BSLEnumType
                or manager._manager_type.snapshot is not root.metadata or manager._manager_type.family!='manager'
                or type(manager._manager_type.metadata_uuid) is not UUID
                or manager._manager_type.metadata_uuid!=definition.identity):
            raise BoundaryViolation('source enumeration type changed')
        _abi(manager._manager_type)
        empty=manager._empty
        if (type(empty) is not BSLEnumReference or empty.value_type is not manager._value_type
                or empty.metadata is not manager._metadata or type(empty.reference_uuid) is not UUID
                or empty.reference_uuid.int!=0):
            raise BoundaryViolation('source enumeration empty reference changed')
        _abi(empty)
        meta=manager._metadata;collection=meta._values
        if (type(collection) is not _DeclaredMetadataCollection or type(collection._items) is not dict
                or any(type(name) is not str for name in collection._items)
                or len(collection._items)!=len(meta._definition.values)):
            raise BoundaryViolation('source enum value metadata mapping changed')
        _abi(collection)
        for definition in meta._definition.values:
            item=collection._items.get(definition.name.casefold())
            if (type(item) is not EnumValueMetadata or item._owner is not meta
                    or item._definition is not definition):
                raise BoundaryViolation('source enum metadata item changed')
            _abi(item)
        if (type(manager._values) is not tuple or type(manager._named) is not dict
                or any(type(name) is not str for name in manager._named)
                or len(manager._values)!=len(manager._metadata._definition.values)
                or len(manager._named)!=len(manager._values)):
            raise BoundaryViolation('source enumeration values changed')
        for definition,reference in zip(manager._metadata._definition.values,manager._values):
            if (type(reference) is not BSLEnumReference or reference.value_type is not manager._value_type
                    or reference.metadata is not manager._metadata or type(reference.reference_uuid) is not UUID
                    or reference.reference_uuid!=definition.identity
                    or manager._named.get(definition.name.casefold()) is not reference):
                raise BoundaryViolation('source enumeration named value changed')
        yield manager


def supports(boundary,value):
    if type(value) in _TYPES:return True
    if type(value) is not _DeclaredMetadataCollection:return False
    root=_root(boundary)
    return value is root.metadata or any(value is manager._metadata._values for manager in _managers(root))


def check(boundary,value):
    root=_root(boundary);_abi(value)
    if value is root or value is root.metadata:
        for manager in _managers(root):pass
        return
    for manager in _managers(root):
        meta=manager._metadata
        if value is manager or value is meta:return
        if type(meta._values) is not _DeclaredMetadataCollection or type(meta._values._items) is not dict:
            raise BoundaryViolation('source enum value metadata changed')
        if value is meta._values:return
        if type(value) is EnumValueMetadata and value._owner is meta and any(value is item for item in meta._values._items.values()):return
        if type(value) is BSLEnumReference and value.value_type is manager._value_type and value.metadata is meta:
            if type(value.reference_uuid) is not UUID:break
            if value.reference_uuid.int==0 or any(value.reference_uuid==item.identity for item in meta._definition.values):return
    raise BoundaryViolation('foreign or retired source enumeration value')


def resolve_metadata_by_type(boundary, receiver, name, *, require_value=False,
                             argument_count=None, allow_references=False):
    """Find the one live source enum declaration, with its ordinary identity."""
    if type(receiver) is not SourceMetadataRoot or receiver is not boundary.app.metadata:
        raise BoundaryViolation('foreign source metadata root')
    if argument_count is not None and argument_count!=1:
        raise TypeError('FindByType requires one argument')

    def find(value):
        boundary._check()
        if receiver is not boundary.app.metadata:
            raise BoundaryViolation('source metadata binding changed')
        if type(value) is not BSLEnumType:
            raise TypeError('FindByType requires a source enumeration Type')
        _abi(value)
        namespace=boundary.app.enumerations
        if (type(namespace) is not BSLEnumerations
                or boundary.vm._metadata._enumerations is not namespace
                or type(namespace._managers) is not dict
                or type(namespace.metadata) is not _DeclaredMetadataCollection
                or type(namespace.metadata._items) is not dict
                or value.snapshot is not namespace.metadata or type(value.name) is not str):
            raise BoundaryViolation('foreign or retired source enumeration type')
        key=value.name.casefold()
        manager=namespace._managers.get(key)
        if (type(manager) is not BSLEnumManager or type(manager._metadata) is not EnumMetadata
                or namespace.metadata._items.get(key) is not manager._metadata
                or type(value.family) is not str
                or not (value is manager._value_type and value.family=='ref'
                        or value is manager._manager_type and value.family=='manager')):
            raise BoundaryViolation('source enumeration type binding changed')
        definition=manager._metadata._definition
        if (type(definition) is not EnumDefinition or type(definition.name) is not str
                or definition.name!=value.name):
            raise BoundaryViolation('source enumeration definition changed')
        # The live manager was created from an admitted declared enum. Use
        # its exact inventory entry, not a walk of the sibling metadata.
        path='Enums/'+definition.name+'.xml'
        if type(receiver._inventory) is not dict or type(receiver._objects) is not dict:
            raise BoundaryViolation('source enumeration metadata inventory changed')
        entry=receiver._inventory.get(path)
        if (type(entry) is not SourceMetadata or type(entry.family) is not str or entry.family!='Enum'
                or type(entry.name) is not str or entry.name!=definition.name
                or type(entry.path) is not str or entry.path!=path):
            raise BoundaryViolation('source enumeration metadata is not declared')
        identities=(definition.identity,value.metadata_uuid,entry.identity)
        if (any(type(item) is not UUID or type(item.int) is not int for item in identities)
                or not identities[0].int==identities[1].int==identities[2].int):
            raise BoundaryViolation('source enumeration metadata identity changed')
        if path not in receiver._objects:
            receiver._objects[path]=SourceMetadataObject(receiver,entry)
        result=receiver._objects[path]
        if (type(result) is not SourceMetadataObject or result._root is not receiver
                or result._entry is not entry or result._parent is not None):
            raise BoundaryViolation('source enumeration metadata binding changed')
        return result

    return boundary.resolve_callable(HostFunction(name,find),require_value=require_value,
                                     allow_references=allow_references)


def namespace(boundary,name):
    if name not in ('enums','перечисления'):return None
    value=_root(boundary);check(boundary,value);return value


def _public(name):
    if type(name) is not str or name.startswith('_'):raise BoundaryViolation('private enumeration member')


def get(boundary,value,name,*,validate=check):
    validate(boundary,value);_public(name)
    try:
        if type(value) is BSLEnumManager and name.casefold() not in value._named and name.casefold() in _ZERO|_ONE:
            result=value.get_method(name)
        else:result=value.get_member(name)
        if type(result) is HostFunction:
            bound=_method(boundary,value,name,result,validate=validate)
            return HostFunction(name,bound,returns_value=result.returns_value,reference_parameters=result.reference_parameters)
        if type(result) in _TYPES or type(result) is _DeclaredMetadataCollection:validate(boundary,result)
        return result
    finally:validate(boundary,value)


def set_member(boundary,value,name):
    check(boundary,value);_public(name)
    def reject(new_value):
        check(boundary,value);raise ValueError('enumerations are read-only')
    return reject


def _method(boundary,value,name,function,*,require_value=False,argument_count=None,allow_references=False,validate=check):
    if type(function) is not HostFunction:raise BoundaryViolation('noncanonical enumeration method')
    key=name.casefold();arity=0 if key in _ZERO else 1 if key in _ONE else None
    if arity is None:raise ValueError('unsupported source enumeration method')
    if argument_count is not None and argument_count!=arity:raise TypeError('invalid enumeration argument count')
    implementation=function.function
    def invoke(*args):
        validate(boundary,value)
        if function.function is not implementation:raise BoundaryViolation('enumeration method changed')
        if len(args)!=arity:raise TypeError('invalid enumeration argument count')
        if type(value) is BSLEnumManager and key in ('indexof','индекс'):
            validate(boundary,args[0])
        try:
            result=function(*args)
            if type(result) in _TYPES or type(result) is _DeclaredMetadataCollection:validate(boundary,result)
            return result
        finally:validate(boundary,value)
    return boundary.resolve_callable(HostFunction(name,invoke,returns_value=function.returns_value,
        reference_parameters=function.reference_parameters),require_value=require_value,allow_references=allow_references)


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False,validate=check):
    validate(boundary,value)
    if name=='__iter__':return lambda:iterate(boundary,value)
    if name=='__setitem__':
        def reject(*args):
            validate(boundary,value);raise ValueError('enumerations are read-only')
        return reject
    if name=='__getitem__':
        if type(value) not in (BSLEnumerations,BSLEnumManager,_DeclaredMetadataCollection):raise ValueError('enum receiver not indexable')
        def index(key):
            validate(boundary,value)
            try:
                result=value.get_index(key);validate(boundary,result);return result
            finally:validate(boundary,value)
        return index
    _public(name)
    if name.casefold() not in _ZERO|_ONE:raise ValueError('unsupported source enumeration method')
    return _method(boundary,value,name,value.get_method(name),require_value=require_value,
        argument_count=argument_count,allow_references=allow_references,validate=validate)


def iterate(boundary,value):
    check(boundary,value)
    if type(value) not in (BSLEnumManager,_DeclaredMetadataCollection):raise ValueError('enumeration receiver is not iterable')
    for item in value:
        check(boundary,value);check(boundary,item);yield item
    check(boundary,value)
