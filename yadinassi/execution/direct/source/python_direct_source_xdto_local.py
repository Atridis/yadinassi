"""Source-created empty scalar XDTO factories; no loaders or IO capabilities."""
from weakref import WeakKeyDictionary,ref,ReferenceType
from types import MethodType
from decimal import Decimal
from . import python_direct_source_xdto as shared
from yadinassi.types.values import HostFunction
from yadinassi.types import values as host_values
_HOST_ABI=host_values._DIRECT_COLLECTION_CLASS_ABI[-1]
from yadinassi.execution.codegen.experimental_naked_boundaries import BoundaryViolation

CONSTRUCTOR_NAMES=('xdtofactory','фабрикаxdto')
_FACTORY=shared._FACTORY;_TYPE=shared._TYPE;_VALUE=shared._VALUE
_FACTORIES=WeakKeyDictionary();_RECEIVERS=WeakKeyDictionary();_VALUES=WeakKeyDictionary()
_BUDGETS=WeakKeyDictionary()
_OWNERS=WeakKeyDictionary()
_RECORDS=WeakKeyDictionary()


def release_application(app):
    _RECORDS.pop(app,None)
    # Cleanup can fail before the host reaches its terminal state. Keep the
    # small weak-key cumulative ledger so failed close cannot refund quotas.

class _Seal:
    pass


def registered(value):
    if not any(type(value) is cls for cls in (_FACTORY,_TYPE,_VALUE)):return False
    shared._hooks()
    return value in _RECEIVERS


def _host_hooks():
    if (shared.io.XS is not shared.io._DIRECT_SOURCE_XDTO_NAMESPACE
            or shared.values.XS is not shared.values._DIRECT_SOURCE_XDTO_NAMESPACE):
        raise BoundaryViolation("local XDTO primitive namespace changed")
    cls,mro,fields=_HOST_ABI
    if host_values.HostFunction is not cls or HostFunction is not cls or cls.__mro__ is not mro:
        raise BoundaryViolation("local XDTO HostFunction binding changed")
    current=vars(cls)
    if len(current)!=len(fields) or any(current.get(k) is not value for k,value in fields):
        raise BoundaryViolation("local XDTO HostFunction hooks changed")


def _fields(value):
    fields=vars(value)
    if type(fields) is not dict or len(fields)>10000 or any(type(k) is not str for k in fields):
        raise BoundaryViolation('local XDTO field mapping changed')
    return fields


def _boundary(boundary):
    from yadinassi.execution.direct.python_direct_source import SourceBoundary
    if type(boundary) is not SourceBoundary:raise BoundaryViolation('local XDTO requires ordinary source boundary')
    _host_hooks();boundary._check();shared._hooks()
    return boundary.app


def _budget(app):
    budget=_BUDGETS.setdefault(app,[0,0,0])
    if budget[0]>32 or budget[1]>min(shared.io.MAX_NODES,shared.values.MAX_NODES) or budget[2]>min(shared.io.MAX_UNITS,shared.values.MAX_UNITS):
        raise ValueError('local XDTO cumulative resource budget exceeded')
    return budget


def _graph(factory):
    # Validate keys before the shared graph code performs any field lookup.
    fields=_fields(factory)
    if set(fields)!={'_nodes','_units','_types','_roots','_packages','_direct_local_xdto'}:
        raise BoundaryViolation('local XDTO factory fields changed')
    pending=[factory._types,factory._roots,factory._packages];seen=set();remaining=10000
    while pending:
        value=pending.pop();kind=type(value)
        if value is factory or value is None or any(kind is cls for cls in (str,int,bool,Decimal)):continue
        if id(value) in seen:continue
        seen.add(id(value));remaining-=1
        if remaining<0:raise BoundaryViolation('local XDTO graph budget exceeded')
        if kind is dict:
            if len(value)>remaining:raise BoundaryViolation('local XDTO graph entry budget exceeded')
            remaining-=len(value)
            for key in value:
                if type(key) is not str and not(type(key) is tuple and len(key)==2 and all(type(n) is str for n in key)):
                    raise BoundaryViolation('local XDTO graph key changed')
            pending.extend(value.values())
        elif kind is tuple:
            if len(value)>remaining:raise BoundaryViolation("local XDTO graph entry budget exceeded")
            remaining-=len(value);pending.extend(value)
        elif any(kind is cls for cls in shared._GRAPH_CLASSES):
            fields=_fields(value)
            if len(fields)>remaining:raise BoundaryViolation("local XDTO graph entry budget exceeded")
            remaining-=len(fields);pending.extend(fields.values())
        else:raise BoundaryViolation('local XDTO graph contains foreign value')
    return shared._graph(factory)


def _seal_graph(saved,current):
    if type(saved) is not tuple or len(saved)!=len(current):
        raise BoundaryViolation('local XDTO seal graph changed')
    def key_ok(key):
        return (type(key) is str or type(key) is int or
                (type(key) is tuple and len(key)==2 and all(type(part) is str for part in key)))
    for record,expected in zip(saved,current):
        if type(record) is not tuple or len(record)!=2 or record[0] is not expected[0]:
            raise BoundaryViolation('local XDTO sealed graph object changed')
        entries=record[1];original=expected[1]
        if type(entries) is not tuple or len(entries)!=len(original):
            raise BoundaryViolation('local XDTO sealed graph entries changed')
        for pair,wanted in zip(entries,original):
            if type(pair) is not tuple or len(pair)!=2 or not key_ok(pair[0]) or not key_ok(wanted[0]):
                raise BoundaryViolation('local XDTO sealed graph key changed')
            if type(pair[0]) is not type(wanted[0]) or pair[0]!=wanted[0] or pair[1] is not wanted[1]:
                raise BoundaryViolation('local XDTO sealed graph value changed')


def _check(boundary,value):
    app=_boundary(boundary)
    if not registered(value):raise BoundaryViolation('local XDTO receiver is not registered')
    factory=_RECEIVERS[value]()
    if factory is None:raise BoundaryViolation('local XDTO factory expired')
    _fields(factory)
    owner=_OWNERS.get(factory)
    if type(owner) is not ReferenceType or owner() is not app:
        raise BoundaryViolation('local XDTO registered owner changed')
    saved=_FACTORIES.get(factory);seal=None if saved is None else saved()
    if type(seal) is not _Seal:raise BoundaryViolation('local XDTO seal changed')
    fields=_fields(seal)
    if (set(fields)!={'application','types','roots','packages','nodes','units','graph'}
            or type(fields['application']) is not ReferenceType
            or type(fields['nodes']) is not int or fields['nodes']<0
            or type(fields['units']) is not int or fields['units']<0):
        raise BoundaryViolation('local XDTO seal fields changed')
    records=_RECORDS.get(app)
    record=None if records is None else records.get(factory)
    if record is None or record[0] is not seal:
        raise BoundaryViolation('local XDTO canonical record missing')
    if (fields['application'] is not record[1] or fields['types'] is not record[2]
            or fields['roots'] is not record[3] or fields['packages'] is not record[4]
            or fields['nodes']!=record[6] or fields['units']!=record[7]):
        raise BoundaryViolation('local XDTO marker differs from canonical record')
    if fields['application']() is not app or factory._direct_local_xdto is not seal:
        raise BoundaryViolation('local XDTO factory owner changed')
    current_graph=_graph(factory)
    if (factory._types is not seal.types or factory._roots is not seal.roots or factory._packages is not seal.packages
            or type(factory._nodes) is not int or type(factory._units) is not int
            or factory._nodes!=seal.nodes or factory._units!=seal.units):
        raise BoundaryViolation('local XDTO factory registry/accounting changed')
    _seal_graph(fields['graph'],record[5])
    _seal_graph(record[5],current_graph);_budget(app)
    if type(value) is _TYPE:shared._kind(factory,value)
    elif type(value) is _VALUE:
        fields=_fields(value);old=_VALUES.get(value)
        if old is None or len(fields)!=len(old) or any(fields.get(k) is not v for k,v in old):
            raise BoundaryViolation('local XDTO scalar value changed')
        shared._kind(factory,value._type)
    return factory,seal


def resolve_constructor(boundary,name,*,require_value=False,argument_count=None,allow_references=False,**unused):
    app=_boundary(boundary);key=name[4:] if name.startswith('new:') else name
    if key not in CONSTRUCTOR_NAMES:raise ValueError('local XDTO constructor unavailable')
    registry=boundary.vm.types
    if type(registry) is not dict or any(type(k) is not str for k in registry):raise BoundaryViolation("local XDTO constructors changed")
    factory=registry.get(key)
    def check(count=None):
        if _boundary(boundary) is not app:raise BoundaryViolation('local XDTO constructor owner changed')
        registry=boundary.vm.types
        if type(registry) is not dict or any(type(k) is not str for k in registry):raise BoundaryViolation('local XDTO constructors changed')
        if type(factory) is HostFunction:_fields(factory)
        if (type(factory) is not HostFunction or factory.function is not _FACTORY or factory.returns_value is not True
                or type(factory.reference_parameters) is not frozenset or factory.reference_parameters or any(registry.get(alias) is not factory for alias in CONSTRUCTOR_NAMES)):
            raise BoundaryViolation('local XDTO constructor binding changed')
        if count is not None and count!=0:raise TypeError('local XDTOFactory takes no arguments')
        budget=_budget(app)
        if budget[0]>=32:raise ValueError('local XDTO factory creation limit exceeded')
        return budget
    check(argument_count)
    def create(*args):
        budget=check(len(args));value=_FACTORY();seal=_Seal()
        seal.application=ref(app);value._direct_local_xdto=seal
        seal.types=value._types;seal.roots=value._roots;seal.packages=value._packages
        seal.nodes=value._nodes;seal.units=value._units;seal.graph=_graph(value)
        _RECORDS.setdefault(app,{})[value]=(seal,seal.application,seal.types,seal.roots,seal.packages,
                                             _graph(value),seal.nodes,seal.units)
        _OWNERS[value]=ref(app)
        _FACTORIES[value]=ref(seal);_RECEIVERS[value]=ref(value)
        for kind in value._types.values():_RECEIVERS[kind]=ref(value)
        budget[0]+=1;_check(boundary,value);return value
    if allow_references:create.requires_reference=lambda index:False
    return create


def get(boundary,value,name):
    factory,_=_check(boundary,value);key=name.casefold()
    if value is factory:
        if key not in shared._METHODS:raise ValueError('local XDTO factory member not integrated')
        return HostFunction(name,shared._METHODS[key].__get__(factory,_FACTORY))
    if type(value) is _VALUE and key in ('value','значение'):return value._value
    raise ValueError('local XDTO member not integrated')


def resolve(boundary,value,name,**contract):
    function=get(boundary,value,name)
    if type(function) is not HostFunction:raise ValueError('local XDTO member is not callable')
    return captured(boundary,function,**contract)


def captured(boundary,function,*,require_value=False,argument_count=None,allow_references=False):
    _host_hooks()
    if type(function) is not HostFunction:return None
    _fields(function)
    if type(function.function) is not MethodType:return None
    callback=function.function;factory=callback.__self__
    if not registered(factory):return None
    operation=callback.__func__
    if operation is not shared._TYPE_CALL and operation is not shared._CREATE_CALL:raise BoundaryViolation('local XDTO method unavailable')
    def check(count=None):
        current,seal=_check(boundary,factory)
        _fields(function)
        if (current is not factory or function.function is not callback or function.returns_value is not True or type(function.reference_parameters) is not frozenset or function.reference_parameters):
            raise BoundaryViolation('local XDTO saved method changed')
        if count is not None and count!=2:raise TypeError('local XDTO Type/Create require two arguments')
        return seal
    check(argument_count)
    def call(*args):
        seal=check(len(args))
        if operation is shared._TYPE_CALL:
            if any(type(v) is not str for v in args):raise TypeError('local XDTO Type requires strings')
            result=operation(factory,*args);check()
            if result is not None:shared._kind(factory,result)
            return result
        kind,value=args
        if not registered(kind) or _check(boundary,kind)[0] is not factory or type(kind) is not _TYPE:
            raise BoundaryViolation('local XDTO requires its own scalar type')
        if not any(type(value) is cls for cls in (str,bool,Decimal)):raise TypeError('local XDTO Create requires scalar input')
        _,lexical=shared.values.scalar(kind,value);budget=_budget(boundary.app)
        if budget[1]+1>min(shared.values.MAX_NODES,shared.io.MAX_NODES) or budget[2]+len(lexical)>min(shared.values.MAX_UNITS,shared.io.MAX_UNITS):
            raise ValueError('local XDTO cumulative allocation budget exceeded')
        result=operation(factory,*args)
        budget[1]+=1;budget[2]+=len(lexical);seal.nodes=factory._nodes;seal.units=factory._units
        record=_RECORDS[boundary.app][factory]
        _RECORDS[boundary.app][factory]=record[:6]+(factory._nodes,factory._units)
        _RECEIVERS[result]=ref(factory);_VALUES[result]=tuple(_fields(result).items())
        check();get(boundary,result,'Value');return result
    if allow_references:call.requires_reference=lambda index:False
    return call
