"""Finite source-owned scalar XDTO Type/Create/Value, without IO grants."""
from types import MethodType
from weakref import ReferenceType,WeakKeyDictionary
from decimal import Decimal
from uuid import UUID
from . import source_xdto_packages as source,xdto_io as io,xdto_values as values
from . import xdto_packages,xdto_schema,xml_io,configuration_xml,configuration_source
from .values import HostFunction
from .experimental_naked_boundaries import BoundaryViolation

_MODULES=(source,io,values,xdto_packages,xdto_schema,xml_io,configuration_xml,configuration_source)
_ABI=tuple((module,module._DIRECT_SOURCE_XDTO_BINDINGS,module._DIRECT_SOURCE_XDTO_CLASSES,module._DIRECT_SOURCE_XDTO_LIMITS) for module in _MODULES)
_FACTORY=io.BSLXDTOFactory;_TYPE=values.BSLXDTOValueType;_VALUE=values.BSLXDTODataValue
_LOADER=source.SourceXDTOPackages;_LOAD=_LOADER.load
_TYPE_CALL=_FACTORY.type;_CREATE_CALL=_FACTORY.create
_METHODS={'type':_TYPE_CALL,'тип':_TYPE_CALL,'create':_CREATE_CALL,'создать':_CREATE_CALL}
_SCALARS=frozenset(('string','boolean','decimal','integer','int','long'))
_CLASSES=tuple(dict.fromkeys(cls for _,_,classes,_ in _ABI for cls,_,_ in classes))
_GRAPH_CLASSES=tuple(cls for cls in _CLASSES if cls.__name__.startswith('BSLXDTO') and cls not in (_FACTORY,_VALUE,values.BSLXDTODataObject,values.BSLXDTOList))
_SEALS=WeakKeyDictionary()
_VALUES=WeakKeyDictionary()


def owns(value):return type(value) is _FACTORY or type(value) is _TYPE or type(value) is _VALUE


def _hooks():
    if (xml_io.expat is not xml_io._DIRECT_SOURCE_XDTO_EXPAT_MODULE
            or configuration_xml.ET is not configuration_xml._DIRECT_SOURCE_XDTO_XML_MODULES[0]
            or configuration_xml.io is not configuration_xml._DIRECT_SOURCE_XDTO_XML_MODULES[1]
            or values.re is not values._DIRECT_SOURCE_XDTO_SCALAR_REGEX[0]):
        raise BoundaryViolation('source XDTO parser module changed')
    writer,name,text=xdto_schema._DIRECT_SOURCE_XDTO_NAME_HELPERS
    if (vars(writer).get('_name') is not name or vars(writer).get('_text') is not text
            or values.re.fullmatch is not values._DIRECT_SOURCE_XDTO_SCALAR_REGEX[1]
            or xml_io.expat.ParserCreate is not xml_io._DIRECT_SOURCE_XDTO_PARSER_CREATE
            or configuration_xml.ET.iterparse is not configuration_xml._DIRECT_SOURCE_XDTO_XML_INPUT[0]
            or configuration_xml.io.StringIO is not configuration_xml._DIRECT_SOURCE_XDTO_XML_INPUT[1]):
        raise BoundaryViolation('source XDTO XML parser hook changed')
    for module,bindings,classes,limits in _ABI:
        for name,expected in bindings:
            if vars(module).get(name) is not expected:raise BoundaryViolation('source XDTO codec binding changed')
        for cls,mro,fields in classes:
            current=vars(cls)
            if cls.__mro__ is not mro or len(current)!=len(fields) or any(current.get(name) is not item for name,item in fields):
                raise BoundaryViolation('source XDTO class hooks changed')
        for name,maximum in limits:
            limit=vars(module).get(name)
            if type(limit) is not int or not 0<limit<=maximum:raise BoundaryViolation('source XDTO quota changed')

    # The package loader owns atomic publication. Refuse mismatched lowered
    # descriptor caps before it can publish beyond the boundary's tighter cap.
    for name in ('MAX_TYPES','MAX_PROPERTIES','MAX_DEPTH'):
        if getattr(xdto_packages,name)>getattr(values,name):
            raise BoundaryViolation('source XDTO descriptor quota aliases differ')
    if source.MAX_PACKAGES>xdto_packages.MAX_PACKAGES:
        raise BoundaryViolation('source XDTO package quota aliases differ')


def _graph(factory):
    """Validate finite canonical fields before any loader traversal/callback."""
    if type(vars(factory)) is not dict:raise BoundaryViolation('source XDTO factory fields changed')
    registry=factory._types
    if type(registry) is not dict or len(registry)>values.MAX_TYPES:raise BoundaryViolation('source XDTO type registry changed')
    for key,kind in registry.items():
        if (type(key) is not tuple or len(key)!=2 or any(type(n) is not str for n in key)
                or (type(kind) is not _TYPE and type(kind) is not values.BSLXDTOObjectType)
                or type(vars(kind)) is not dict or kind._factory is not factory or type(kind._uri) is not str or type(kind._name) is not str
                or key!=(kind._uri,kind._name)):
            raise BoundaryViolation('source XDTO type ownership changed')
    pending=[registry,factory._roots,factory._packages];seen=set();result=[];entries_left=10000
    while pending:
        value=pending.pop();kind=type(value)
        if value is factory or value is None or any(kind is cls for cls in (str,bool,int,Decimal)):continue
        if id(value) in seen:continue
        seen.add(id(value))
        if len(seen)>10000:raise BoundaryViolation('source XDTO graph exceeds limit')
        if kind is dict:
            entries_left-=len(value)
            if entries_left<0:raise BoundaryViolation('source XDTO graph entry budget exceeded')
            for key in value:
                if type(key) is not str and not (type(key) is tuple and all(type(n) is str for n in key)):
                    raise BoundaryViolation('source XDTO graph key changed')
            entries=tuple(value.items());result.append((value,entries));pending.extend(v for _,v in entries)
        elif kind is tuple:
            entries_left-=len(value)
            if entries_left<0:raise BoundaryViolation('source XDTO graph entry budget exceeded')
            result.append((value,tuple(enumerate(value))));pending.extend(value)
        elif any(kind is cls for cls in _GRAPH_CLASSES):
            fields=vars(value)
            if type(fields) is not dict:raise BoundaryViolation('source XDTO graph field mapping changed')
            if any(type(name) is not str or not name.startswith('_') for name in fields):raise BoundaryViolation('source XDTO graph field changed')
            entries_left-=len(fields)
            if entries_left<0:raise BoundaryViolation('source XDTO graph entry budget exceeded')
            entries=tuple(fields.items());result.append((value,entries));pending.extend(fields.values())
        else:raise BoundaryViolation('source XDTO graph contains foreign fields')
    return tuple(result)


def _same_graph(seal):
    for obj,entries in seal:
        current=obj if type(obj) is dict else dict(enumerate(obj)) if type(obj) is tuple else vars(obj)
        if type(current) is not dict or len(current)!=len(entries) or any(current.get(key) is not value for key,value in entries):
            raise BoundaryViolation('source XDTO descriptor graph changed')


def _inventory_seal(inventory):
    return None if inventory is None else (tuple(inventory[0].items()),tuple(inventory[1]),frozenset(inventory[2]))


def _seal(owner,app,factory):
    return (owner,app.source,app.files,tuple(app.files.items()),
            tuple((item,tuple((name,getattr(item,name)) for name in ('identity','family','name','path'))) for item in app.source.metadata),
            factory._types,factory._roots,factory._packages,_graph(factory),factory._nodes,factory._units,
            owner._direct_scalar_primitives,owner._inventory,owner._loaded,frozenset(owner._loaded),owner._bytes,_inventory_seal(owner._inventory),app.source.metadata)


def _verify(seal,owner,app,factory):
    if (owner is not seal[0] or app.source is not seal[1] or app.files is not seal[2]
            or len(app.files)!=len(seal[3]) or any(app.files.get(k) is not v for k,v in seal[3])
            or factory._types is not seal[5] or factory._roots is not seal[6] or factory._packages is not seal[7]
            or factory._nodes!=seal[9] or factory._units!=seal[10]
            or owner._direct_scalar_primitives is not seal[11] or owner._inventory is not seal[12]
            or owner._loaded is not seal[13] or owner._loaded!=seal[14] or owner._bytes!=seal[15]):
        raise BoundaryViolation('source XDTO ownership or accounting changed')
    if app.source.metadata is not seal[17] or len(app.source.metadata)!=len(seal[4]) or any(item is not old for item,(old,_) in zip(app.source.metadata,seal[4])):
        raise BoundaryViolation('source XDTO metadata replaced')
    for item,fields in seal[4]:
        if any(getattr(item,name) is not v for name,v in fields):raise BoundaryViolation('source XDTO metadata fields changed')
    if owner._inventory is not None:
        inventory=owner._inventory;old=seal[16]
        if (old is None or len(inventory[0])!=len(old[0]) or any(inventory[0].get(k) is not v for k,v in old[0])
                or tuple(inventory[1])!=old[1] or inventory[2]!=old[2]):
            raise BoundaryViolation('source XDTO inventory contents changed')
    _same_graph(seal[8])


def _owner(boundary):
    from .python_direct_source import SourceBoundary
    if type(boundary) is not SourceBoundary:raise BoundaryViolation('source XDTO requires ordinary source boundary')
    boundary._check();_hooks();app=boundary.app;owner=app.xdto
    if type(owner) is not _LOADER or type(vars(owner)) is not dict or type(owner._application) is not ReferenceType or owner._application() is not app:
        raise BoundaryViolation('source XDTO owner changed')
    factory=owner.factory
    if type(factory) is not _FACTORY or type(vars(factory)) is not dict:raise BoundaryViolation('source XDTO factory changed')
    loader=getattr(factory,'_source_packages_loader',None)
    if type(loader) is not MethodType or loader.__self__ is not owner or loader.__func__ is not _LOAD:
        raise BoundaryViolation('source XDTO loader changed')
    if any(name in vars(owner) for name in ('load','_definitions')) or any(name in vars(factory) for name in ('type','create','_kind','_reserve')):
        raise BoundaryViolation('source XDTO instance hooks changed')
    if (type(app.files) is not dict or any(type(k) is not str or type(v) is not bytes for k,v in app.files.items())
            or type(app.source) is not configuration_source.ConfigurationSource or type(app.source.metadata) is not tuple):
        raise BoundaryViolation('source XDTO metadata inventory changed')
    for item in app.source.metadata:
        if type(item) is not configuration_source.SourceMetadata or any(type(getattr(item,n)) is not str for n in ('family','name','path')) or type(item.identity) is not UUID:
            raise BoundaryViolation('source XDTO metadata entry changed')
    if (type(owner._loaded) is not set or any(type(v) is not str for v in owner._loaded)
            or len(owner._loaded)>xdto_packages.MAX_PACKAGES or type(owner._bytes) is not int
            or not 0<=owner._bytes<=source.MAX_SCHEMA_BYTES):raise BoundaryViolation('source XDTO load accounting changed')
    if owner._inventory is not None:
        inventory=owner._inventory
        if (type(inventory) is not tuple or len(inventory)!=3 or type(inventory[0]) is not dict
                or type(inventory[1]) is not list or type(inventory[2]) is not set
                or any(type(x) is not str for x in (*inventory[1],*inventory[2]))
                or any(type(k) is not str or not any(v is item for item in app.source.metadata) for k,v in inventory[0].items())):
            raise BoundaryViolation('source XDTO cached inventory changed')
    for field,maximum in (('_nodes',values.MAX_NODES),('_units',values.MAX_UNITS)):
        value=getattr(factory,field)
        if type(value) is not int or not 0<=value<=maximum:raise BoundaryViolation('source XDTO allocation budget changed')
    graph=_graph(factory)
    primitive_seal=owner._direct_scalar_primitives
    if source._DIRECT_SOURCE_XDTO_PRIMITIVES.get(app) is not primitive_seal:raise BoundaryViolation("source XDTO initial seal replaced")
    if type(primitive_seal) is not tuple or len(primitive_seal)!=6 or primitive_seal[0] is not factory or type(primitive_seal[1]) is not tuple:
        raise BoundaryViolation('source XDTO primitive seal changed')
    for entry in primitive_seal[1]:
        if type(entry) is not tuple or len(entry)!=3:raise BoundaryViolation('source XDTO primitive seal changed')
        key,kind,fields=entry
        if type(key) is not tuple or len(key)!=2 or any(type(n) is not str for n in key) or type(kind) is not _TYPE or type(vars(kind)) is not dict or type(fields) is not tuple:
            raise BoundaryViolation('source XDTO primitive seal changed')
        if factory._types.get(key) is not kind or len(vars(kind))!=len(fields):raise BoundaryViolation('source XDTO primitive changed')
        for field in fields:
            if type(field) is not tuple or len(field)!=2 or type(field[0]) is not str or vars(kind).get(field[0]) is not field[1]:
                raise BoundaryViolation('source XDTO primitive fields changed')
    seal=_SEALS.get(app)
    if seal is not None:_verify(seal,owner,app,factory)
    else:
        if (factory._types is not primitive_seal[2] or factory._roots is not primitive_seal[3]
                or factory._packages is not primitive_seal[4] or factory._roots):
            raise BoundaryViolation('source XDTO initial factory roots changed')
        _same_graph(primitive_seal[5])
        if len(factory._types)!=len(primitive_seal[1]):raise BoundaryViolation('source XDTO initial registry changed')
        if owner._inventory is not None:raise BoundaryViolation('source XDTO preloaded inventory not yet integrated')
        if owner._loaded:raise BoundaryViolation('source XDTO preloaded factory not yet integrated')
        if any(kind._base is not None or kind._uri!=values.XS for kind in factory._types.values()):
            raise BoundaryViolation('source XDTO initial descriptor changed')
        _SEALS[app]=_seal(owner,app,factory)
    return owner,factory


def namespace(boundary,name):
    if name not in ('xdtofactory','фабрикаxdto'):return None
    return _owner(boundary)[1]


def _kind(factory,kind):
    if (type(kind) is not _TYPE or kind._factory is not factory or type(kind._uri) is not str or type(kind._name) is not str or factory._types.get((kind._uri,kind._name)) is not kind):
        raise BoundaryViolation('source XDTO requires a current scalar type from this factory')
    base=kind._base
    if base is not None:
        if (type(base) is not _TYPE or base._factory is not factory or base._uri!=values.XS
                or base._base is not None or factory._types.get((base._uri,base._name)) is not base):
            raise BoundaryViolation('source XDTO scalar base changed')
    primitive=kind if base is None else base
    if primitive._uri!=values.XS or primitive._name not in _SCALARS:raise ValueError('source XDTO scalar type not integrated')


def get(boundary,value,name):
    from . import python_direct_source_xdto_local as local
    if local.registered(value):return local.get(boundary,value,name)
    _,factory=_owner(boundary)
    if value is factory:
        key=name.casefold()
        if key not in _METHODS:raise ValueError('source XDTO factory member not integrated')
        return HostFunction(name,_METHODS[key].__get__(factory,_FACTORY))
    if type(value) is _VALUE:
        if type(vars(value)) is not dict:raise BoundaryViolation('source XDTO value field mapping changed')
        saved=_VALUES.get(value)
        if saved is None or any(getattr(value,name) is not old for name,old in saved):
            raise BoundaryViolation('source XDTO value was not produced here or changed')
        _kind(factory,value._type)
        if value._factory is not factory:raise BoundaryViolation('foreign source XDTO value')
        if not any(type(value._value) is cls for cls in (str,bool,Decimal)) or type(value._lexical) is not str:raise BoundaryViolation('source XDTO value fields changed')
        if name.casefold() in ('value','значение'):return value._value
    raise ValueError('source XDTO member not integrated')


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False):
    from . import python_direct_source_xdto_local as local
    if local.registered(value):return local.resolve(boundary,value,name,require_value=require_value,argument_count=argument_count,allow_references=allow_references)
    function=get(boundary,value,name)
    if type(function) is not HostFunction:raise ValueError('source XDTO member is not callable')
    return captured(boundary,function,require_value=require_value,argument_count=argument_count,allow_references=allow_references)


def captured(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    from . import python_direct_source_xdto_local as local
    bound=local.captured(boundary,function,require_value=require_value,argument_count=argument_count,allow_references=allow_references)
    if bound is not None:return bound
    if type(function) is not HostFunction or type(function.function) is not MethodType:return None
    callback=function.function;factory=callback.__self__
    if type(factory) is not _FACTORY:return None
    operation=callback.__func__
    if operation is not _TYPE_CALL and operation is not _CREATE_CALL:raise BoundaryViolation('source XDTO method not integrated')
    def check(count=None):
        owner,current=_owner(boundary)
        if current is not factory or function.function is not callback or function.returns_value is not True or function.reference_parameters:
            raise BoundaryViolation('source XDTO saved method changed')
        if count is not None and count!=2:raise TypeError('source XDTO Type/Create require two arguments')
        return owner
    check(argument_count)
    def call(*args):
        owner=check(len(args))
        if operation is _TYPE_CALL:
            if any(type(v) is not str for v in args):raise TypeError('source XDTO Type requires strings')
            try:result=operation(factory,*args)
            except Exception:
                # Namespace inventory is a legitimate cache even when the
                # candidate graph fails. Preserve the old published graph seal.
                previous=_SEALS[boundary.app]
                if previous[12] is None:
                    _SEALS[boundary.app]=previous[:12]+(owner._inventory,)+previous[13:16]+(_inventory_seal(owner._inventory),previous[17])
                check()
                raise
            # Canonical loader completed its atomic publication. Accept only its
            # new graph; old descriptor identities were validated before entry.
            _SEALS[boundary.app]=_seal(owner,boundary.app,factory)
            check()
            if result is not None:_kind(factory,result)
            return result
        _kind(factory,args[0])
        if not any(type(args[1]) is cls for cls in (str,bool,Decimal)):raise TypeError('source XDTO Create requires scalar input')
        # Imported quota aliases may be lowered independently. Admit against
        # the tightest current cap before the canonical constructor can reserve.
        _,lexical=values.scalar(args[0],args[1])
        if (factory._nodes+1>min(values.MAX_NODES,io.MAX_NODES)
                or factory._units+len(lexical)>min(values.MAX_UNITS,io.MAX_UNITS)):
            raise ValueError('source XDTO scalar allocation exceeds resource budget')
        result=operation(factory,*args)
        # Only the canonical scalar constructor may advance these budgets.
        _SEALS[boundary.app]=_seal(owner,boundary.app,factory)
        if type(result) is not _VALUE:raise BoundaryViolation('source XDTO constructor result changed')
        _VALUES[result]=tuple((name,getattr(result,name)) for name in ('_factory','_type','_value','_lexical'))
        check();get(boundary,result,'Value');return result
    if allow_references:call.requires_reference=lambda index:False
    return call
