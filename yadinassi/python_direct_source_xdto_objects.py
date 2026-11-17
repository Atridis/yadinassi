"""Global source XDTO flat scalar objects, without list, graph or IO grants."""
from weakref import WeakKeyDictionary
from decimal import Decimal
from . import python_direct_source_xdto as shared
from .experimental_naked_boundaries import BoundaryViolation

_OBJECT=shared.values.BSLXDTODataObject
_TYPE=shared.values.BSLXDTOObjectType
_PROPERTY=shared.values.BSLXDTOProperty
_PROPERTIES=shared.values.BSLXDTOPropertyCollection
_SET=_OBJECT.set
_RECORDS=WeakKeyDictionary()


def release_application(app):
    _RECORDS.pop(app,None)


def owns(value):return type(value) is _OBJECT


def _fields(value):
    result=vars(value)
    if type(result) is not dict or len(result)>10000 or any(type(k) is not str for k in result):
        raise BoundaryViolation('source XDTO object fields changed')
    return result


def _hooks():
    if shared.values.NULL is not shared.values._DIRECT_SOURCE_XDTO_NULL:
        raise BoundaryViolation('source XDTO Null binding changed')


def admit_type(factory,kind):
    if type(kind) is not _TYPE:raise BoundaryViolation('source XDTO requires exact object type')
    _fields(kind)
    if (kind._factory is not factory or type(kind._uri) is not str or type(kind._name) is not str
            or factory._types.get((kind._uri,kind._name)) is not kind or kind._base is not None):
        raise BoundaryViolation('source XDTO object type ownership changed')
    collection=kind._properties
    if type(collection) is not _PROPERTIES:raise BoundaryViolation('source XDTO property collection changed')
    _fields(collection);items=collection._items
    if type(items) is not tuple or len(items)>shared.values.MAX_PROPERTIES:
        raise BoundaryViolation('source XDTO property inventory changed')
    names=set()
    for prop in items:
        if type(prop) is not _PROPERTY:raise BoundaryViolation('source XDTO property changed')
        _fields(prop)
        if (prop._owner is not kind or type(prop._name) is not str or type(prop._uri) is not str
                or type(prop._upper) is not int or type(prop._lower) is not int
                or type(prop._nil) is not bool or type(prop._attribute) is not bool):
            raise BoundaryViolation('source XDTO property ownership/shape changed')
        if prop._upper!=1 or prop._lower not in (0,1) or prop._name in names:
            raise ValueError('source XDTO requires a whole flat single-valued object type')
        names.add(prop._name)
        if type(prop._type) is not shared._TYPE:
            raise ValueError('source XDTO nested/list object types not integrated')
        _fields(prop._type);shared._kind(factory,prop._type)
    return items


def _snapshot(obj):
    return (obj._factory,obj._type,obj._values,tuple((name,value,
            None if value is None else tuple(_fields(value).items())) for name,value in obj._values.items()))


def _check(boundary,obj):
    owner,factory=shared._owner(boundary);_hooks()
    if not owns(obj):raise BoundaryViolation('source XDTO object receiver changed')
    fields=_fields(obj)
    if set(fields)!={'_factory','_type','_owner','_owning','_values'}:
        raise BoundaryViolation('source XDTO object instance hooks changed')
    records=_RECORDS.get(boundary.app)
    old=None if records is None else records.get(obj)
    if (old is None or obj._factory is not factory or obj._factory is not old[0] or obj._type is not old[1]
            or obj._values is not old[2] or obj._owner is not None or obj._owning is not None):
        raise BoundaryViolation('source XDTO object provenance changed')
    items=admit_type(factory,obj._type);values=obj._values
    if type(values) is not dict or any(type(k) is not str for k in values) or len(values)!=len(old[3]):
        raise BoundaryViolation('source XDTO object value mapping changed')
    for name,child,saved in old[3]:
        if values.get(name) is not child or name not in values:raise BoundaryViolation('source XDTO object property changed')
        prop=next((p for p in items if p._name==name),None)
        if prop is None:raise BoundaryViolation('source XDTO object property no longer declared')
        if child is None:
            if not prop._nil:raise BoundaryViolation('source XDTO object null changed')
        else:
            if type(child) is not shared._VALUE:raise BoundaryViolation('source XDTO object scalar changed')
            current=_fields(child)
            if len(current)!=len(saved) or any(current.get(k) is not v for k,v in saved):
                raise BoundaryViolation('source XDTO object scalar fields changed')
            if child._factory is not factory or child._type is not prop._type:
                raise BoundaryViolation('source XDTO object scalar ownership changed')
    return owner,factory,items


def create(boundary,kind):
    owner,factory=shared._owner(boundary);_hooks();admit_type(factory,kind)
    if factory._nodes+1>min(shared.values.MAX_NODES,shared.io.MAX_NODES) or factory._units>min(shared.values.MAX_UNITS,shared.io.MAX_UNITS):
        raise ValueError('source XDTO object allocation exceeds resource budget')
    result=shared._CREATE_CALL(factory,kind)
    shared._SEALS[boundary.app]=shared._seal(owner,boundary.app,factory)
    if type(result) is not _OBJECT:raise BoundaryViolation('source XDTO object constructor changed')
    _RECORDS.setdefault(boundary.app,{})[result]=_snapshot(result);_check(boundary,result)
    return result


def _property(items,name):
    if type(name) is not str:raise TypeError('source XDTO property requires String')
    prop=next((p for p in items if p._name==name),None)
    if prop is None:raise ValueError('XDTO: неизвестное свойство')
    return prop


def get(boundary,obj,name):
    _,_,items=_check(boundary,obj);prop=_property(items,name)
    value=obj._values.get(prop._name)
    return None if value is None else value._value


def set_member(boundary,obj,name):
    _,_,items=_check(boundary,obj);prop=_property(items,name)
    def assign(value):
        owner,factory,current=_check(boundary,obj)
        if _property(current,name) is not prop:raise BoundaryViolation('source XDTO bound property changed')
        if value is None or value is shared.values._DIRECT_SOURCE_XDTO_NULL:
            if not prop._nil:raise ValueError('XDTO: пустое значение не разрешено')
            cost=0;nodes=0
        else:
            if not any(type(value) is cls for cls in (str,bool,Decimal)):
                raise TypeError('source XDTO flat property requires primitive scalar')
            _,lexical=shared.values.scalar(prop._type,value);cost=len(lexical);nodes=1
        if (factory._nodes+nodes>min(shared.values.MAX_NODES,shared.io.MAX_NODES)
                or factory._units+cost>min(shared.values.MAX_UNITS,shared.io.MAX_UNITS)):
            raise ValueError('source XDTO property allocation exceeds resource budget')
        _SET(obj,name,value)
        shared._SEALS[boundary.app]=shared._seal(owner,boundary.app,factory)
        _RECORDS[boundary.app][obj]=_snapshot(obj);_check(boundary,obj)
    return assign
