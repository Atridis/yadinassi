"""Bounded source-owned XDTO trees and lists, without descriptor or IO grants."""
from weakref import WeakKeyDictionary
from types import MethodType
from decimal import Decimal
from . import python_direct_source_xdto as shared
from .values import HostFunction
from .experimental_naked_boundaries import BoundaryViolation

_OBJECT=shared.values.BSLXDTODataObject
_TYPE=shared.values.BSLXDTOObjectType
_LIST=shared.values.BSLXDTOList
_PROPERTY=shared.values.BSLXDTOProperty
_PROPERTIES=shared.values.BSLXDTOPropertyCollection
_RECORDS=WeakKeyDictionary()
_METHODS={}
for _method,_arity,_returns,_names in (
    ('count',(0,),True,('count','количество')),('get',(1,),True,('get','получить')),
    ('get_xdto',(1,),True,('getxdto','получитьxdto')),('add',(1,),True,('add','добавить')),
    ('insert',(2,),True,('insert','вставить')),('set',(2,),True,('set','установить')),
    ('delete',(0,1),True,('delete','удалить')),('clear',(0,),False,('clear','очистить'))):
    for _name in _names:_METHODS[_name]=(getattr(_LIST,_method),_arity,_returns,_method)
_UNSET=_OBJECT.unset
_GET_LIST=_OBJECT.get_list
_SET=_OBJECT.set
_MUTATIONS=frozenset(('add','insert','set','delete','clear','unset'))


def release_application(app):_RECORDS.pop(app,None)
def owns(value):return type(value) is _OBJECT or type(value) is _LIST


def _fields(value):
    result=vars(value)
    if type(result) is not dict or len(result)>10000 or any(type(k) is not str for k in result):
        raise BoundaryViolation('source XDTO object fields changed')
    return result


def _hooks():
    if shared.values.NULL is not shared.values._DIRECT_SOURCE_XDTO_NULL:
        raise BoundaryViolation('source XDTO Null binding changed')


def admit_type(factory,kind):
    pending=[(kind,0)];seen=set();root=None;total=0
    while pending:
        current,depth=pending.pop()
        if id(current) in seen:continue
        seen.add(id(current))
        if type(current) is not _TYPE or depth>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH) or len(seen)>shared.values.MAX_TYPES:
            raise BoundaryViolation('source XDTO object type graph exceeds bounds')
        _fields(current)
        if (current._factory is not factory or type(current._uri) is not str or type(current._name) is not str
                or factory._types.get((current._uri,current._name)) is not current or current._base is not None):
            raise BoundaryViolation('source XDTO object type ownership changed')
        collection=current._properties
        if type(collection) is not _PROPERTIES:raise BoundaryViolation('source XDTO property collection changed')
        _fields(collection);items=collection._items
        if type(items) is not tuple:raise BoundaryViolation('source XDTO property inventory changed')
        total+=len(items)
        if total>shared.values.MAX_TYPES*shared.values.MAX_PROPERTIES or len(items)>shared.values.MAX_PROPERTIES:
            raise BoundaryViolation('source XDTO property inventory exceeds bounds')
        if current is kind:root=items
        names=set()
        for prop in items:
            if type(prop) is not _PROPERTY:raise BoundaryViolation('source XDTO property changed')
            _fields(prop)
            if (prop._owner is not current or type(prop._name) is not str or type(prop._uri) is not str
                    or type(prop._upper) is not int or type(prop._lower) is not int
                    or type(prop._nil) is not bool or type(prop._attribute) is not bool):
                raise BoundaryViolation('source XDTO property ownership/shape changed')
            if (prop._lower<0 or prop._lower>shared.values.MAX_LIST or prop._upper==0 or prop._upper < -1
                    or (prop._upper!=-1 and prop._lower>prop._upper) or prop._name in names):
                raise ValueError('source XDTO property bounds unavailable')
            names.add(prop._name)
            if type(prop._type) is _TYPE:pending.append((prop._type,depth+1))
            elif type(prop._type) is shared._TYPE:
                _fields(prop._type);shared._kind(factory,prop._type)
            else:raise ValueError('source XDTO property type not integrated')
    return root


def _snapshot(value):
    fields=tuple(_fields(value).items())
    if type(value) is _OBJECT:return fields,value._values,tuple(value._values.items())
    if type(value) is _LIST:return fields,value._items,tuple(value._items)
    return fields,None,()


def _record(boundary,*values):
    records=_RECORDS.setdefault(boundary.app,{})
    for value in values:
        if value is None:continue
        if not any(type(value) is cls for cls in (_OBJECT,_LIST,shared._VALUE)):
            raise BoundaryViolation('source XDTO canonical result changed')
        records[value]=_snapshot(value)
        if type(value) is shared._VALUE:shared._VALUES[value]=tuple(_fields(value).items())


def _check(boundary,target):
    owner,factory=shared._owner(boundary);_hooks()
    if not owns(target):raise BoundaryViolation('source XDTO receiver changed')
    records=_RECORDS.get(boundary.app)
    if records is None or target not in records:raise BoundaryViolation('source XDTO receiver not produced here')
    if len(records)>shared.values.MAX_NODES:raise BoundaryViolation('source XDTO value inventory exceeds bounds')
    types={}
    # Check the entire bounded private value inventory before native traversal.
    for value,(saved,container,entries) in records.items():
        current=_fields(value)
        if len(current)!=len(saved) or any(current.get(k) is not v for k,v in saved):
            raise BoundaryViolation('source XDTO value fields changed')
        if type(value) is _OBJECT:
            if set(current)!={'_factory','_type','_owner','_owning','_values'} or value._factory is not factory:
                raise BoundaryViolation('source XDTO object ownership changed')
            if value._type not in types:types[value._type]=admit_type(factory,value._type)
            values=value._values
            if type(values) is not dict or any(type(k) is not str for k in values) or values is not container or len(values)!=len(entries):
                raise BoundaryViolation('source XDTO value mapping changed')
            if any(k not in values or values[k] is not v for k,v in entries):raise BoundaryViolation('source XDTO properties changed')
        elif type(value) is _LIST:
            if set(current)!={'_owner','_prop','_items'} or type(value._items) is not list or value._items is not container:
                raise BoundaryViolation('source XDTO list fields changed')
            if len(value._items)!=len(entries) or any(a is not b for a,b in zip(value._items,entries)):
                raise BoundaryViolation('source XDTO list entries changed')
        elif type(value) is not shared._VALUE:raise BoundaryViolation('source XDTO value inventory changed')
    for value in records:
        if type(value) is shared._VALUE:continue
        if type(value) is _LIST:
            parent=value._owner;prop=value._prop
            if type(parent) is not _OBJECT or parent not in records or not any(prop is p for p in types[parent._type]) or prop._upper==1:
                raise BoundaryViolation('source XDTO list ownership changed')
            live=parent._values.get(prop._name) is value
            if not live and value._items:raise BoundaryViolation('source XDTO orphan list contains values')
            cap=min(shared.values.MAX_LIST,prop._upper if prop._upper>=0 else shared.values.MAX_LIST)
            if len(value._items)>cap:raise BoundaryViolation('source XDTO list exceeds bounds')
            children=((prop,child) for child in value._items)
        else:
            parent=value
            children=[]
            for name,child in value._values.items():
                prop=_property(types[value._type],name)
                if prop._upper!=1:
                    if type(child) is not _LIST or child not in records or child._owner is not value or child._prop is not prop:
                        raise BoundaryViolation('source XDTO property list changed')
                    continue
                children.append((prop,child))
            trail=value;visited=set();depth=0
            while trail is not None:
                if type(trail) is not _OBJECT or trail not in records or id(trail) in visited or depth>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH):
                    raise BoundaryViolation('source XDTO cyclic or excessive ownership')
                visited.add(id(trail));depth+=1
                ancestor=trail._owner
                if ancestor is not None:
                    if type(ancestor) is not _OBJECT or ancestor not in records:raise BoundaryViolation('source XDTO foreign owner')
                    prop=trail._owning
                    if not any(prop is p for p in types[ancestor._type]):raise BoundaryViolation('source XDTO owning property changed')
                    slot=ancestor._values.get(prop._name)
                    if prop._upper==1:
                        if slot is not trail:raise BoundaryViolation('source XDTO owner backlink changed')
                    elif type(slot) is not _LIST or slot not in records or sum(c is trail for c in slot._items)!=1:
                        raise BoundaryViolation('source XDTO list backlink changed')
                elif trail._owning is not None:raise BoundaryViolation('source XDTO detached property changed')
                trail=ancestor
        for prop,child in children:
            if child is None:
                if not prop._nil:raise BoundaryViolation('source XDTO null changed')
            elif not any(type(child) is cls for cls in (_OBJECT,shared._VALUE)) or child not in records:
                raise BoundaryViolation('source XDTO unregistered child')
            elif child._factory is not factory or child._type is not prop._type:
                raise BoundaryViolation('source XDTO child type changed')
            elif type(child) is _OBJECT and (child._owner is not parent or child._owning is not prop):
                raise BoundaryViolation('source XDTO child ownership changed')
    return owner,factory,types.get(target._type) if type(target) is _OBJECT else target._prop


def _budget(factory,nodes=0,units=0):
    if (factory._nodes+nodes>min(shared.values.MAX_NODES,shared.io.MAX_NODES)
            or factory._units+units>min(shared.values.MAX_UNITS,shared.io.MAX_UNITS)):
        raise ValueError('source XDTO allocation exceeds resource budget')


def _publish(boundary,owner,factory,*changed):
    shared._SEALS[boundary.app]=shared._seal(owner,boundary.app,factory)
    _record(boundary,*changed)


def create(boundary,kind):
    records=_RECORDS.get(boundary.app)
    if records:_check(boundary,next(iter(records)))
    owner,factory=shared._owner(boundary);_hooks();admit_type(factory,kind);_budget(factory,1)
    result=shared._CREATE_CALL(factory,kind)
    if type(result) is not _OBJECT:raise BoundaryViolation('source XDTO object constructor changed')
    _publish(boundary,owner,factory,result);_check(boundary,result);return result


def _property(items,name):
    if type(name) is not str:raise TypeError('source XDTO property requires String')
    prop=next((p for p in items if p._name==name),None)
    if prop is None:raise ValueError('XDTO: неизвестное свойство')
    return prop


def _native(value):return value._value if type(value) is shared._VALUE else value


def get(boundary,obj,name):
    owner,factory,items=_check(boundary,obj)
    if type(obj) is _LIST:
        method,_,returns,_=_method(obj,name)
        return HostFunction(name,method.__get__(obj,_LIST),returns_value=returns)
    prop=_property(items,name)
    if prop._upper!=1:
        if prop._name not in obj._values:
            _budget(factory,1);result=_GET_LIST(obj,prop._name)
            _publish(boundary,owner,factory,obj,result);_check(boundary,obj)
        return obj._values[prop._name]
    return _native(obj._values.get(prop._name))


def _input(boundary,owner,prop,value,old=None,present=False):
    if present and value is old:return 0,0
    if value is None or value is shared.values._DIRECT_SOURCE_XDTO_NULL:
        if not prop._nil:raise ValueError('XDTO: пустое значение не разрешено')
        return 0,0
    if type(prop._type) is _TYPE:
        if type(value) is not _OBJECT:raise TypeError('source XDTO property requires owned object')
        _check(boundary,value)
        if value._type is not prop._type or value._owner is not None:raise ValueError('source XDTO object type/owner mismatch')
        # Check the prospective complete tree against the tightest alias before
        # native _prepare (which sees only values.MAX_DEPTH) can attach anything.
        depth=0;ancestor=owner
        while ancestor is not None:
            if ancestor is value:raise ValueError('XDTO: цикл владения')
            depth+=1;ancestor=ancestor._owner
        pending=[(value,depth)]
        while pending:
            node,level=pending.pop()
            if level>min(shared.values.MAX_DEPTH,shared.io.MAX_DEPTH):
                raise ValueError('source XDTO ownership depth exceeded')
            for child in node._values.values():
                for item in child._items if type(child) is _LIST else (child,):
                    if type(item) is _OBJECT:pending.append((item,level+1))
        return 0,0
    if not any(type(value) is cls for cls in (str,bool,Decimal)):
        raise TypeError('source XDTO property requires primitive scalar')
    _,lexical=shared.values.scalar(prop._type,value)
    return 1,len(lexical)


def set_member(boundary,obj,name):
    if type(obj) is not _OBJECT:
        _check(boundary,obj);raise ValueError('source XDTO list properties are read-only')
    _,_,items=_check(boundary,obj);prop=_property(items,name)
    if prop._upper!=1:raise ValueError('XDTO: используйте методы списка')
    def assign(value):
        owner,factory,current=_check(boundary,obj)
        if _property(current,name) is not prop:raise BoundaryViolation('source XDTO bound property changed')
        old=obj._values.get(name);nodes,units=_input(boundary,obj,prop,value,old,name in obj._values)
        _budget(factory,nodes,units);_SET(obj,name,value)
        _publish(boundary,owner,factory,obj,old,obj._values[name]);_check(boundary,obj)
    return assign


def _method(value,name):
    if type(name) is not str:raise TypeError('source XDTO method requires String')
    if type(value) is _OBJECT:
        if name.casefold() in ('unset','сбросить'):return _UNSET,(1,),False,'unset'
    else:
        key={'__getitem__':'get','__setitem__':'set'}.get(name,name.casefold())
        if key in _METHODS:return _METHODS[key]
    raise ValueError('source XDTO method not integrated')


def resolve(boundary,value,name,*,require_value=False,argument_count=None,allow_references=False,validate=None):
    _check(boundary,value)
    if name=="__iter__":
        if type(value) is not _LIST:raise ValueError("source XDTO object is not iterable")
        return lambda:iterate(boundary,value)
    method,arity,returns,operation=_method(value,name)
    def check(count=None):
        result=_check(boundary,value)
        if validate is not None:validate()
        if require_value and not returns:raise ValueError('source XDTO procedure cannot be used as value')
        if count is not None and count not in arity:raise TypeError('source XDTO invalid method arity')
        if operation in _MUTATIONS and type(value) is _LIST and value._owner._values.get(value._prop._name) is not value:
            raise ValueError('source XDTO orphan list is read-only')
        return result
    check(argument_count)
    def call(*args):
        owner,factory,items=check(len(args));changed=[value];nodes=units=0
        if operation=='unset':
            prop=_property(items,args[0]);old=value._values.get(prop._name)
            if type(old) is _LIST:changed.extend(old._items);changed.append(old)
            else:changed.append(old)
        elif operation in ('add','insert','set'):
            prop=value._prop;parent=value._owner
            if operation=='add':index=len(value._items);incoming=args[0]
            else:
                if not (type(args[0]) is int or type(args[0]) is Decimal):raise ValueError('source XDTO index requires Number')
                index=shared.values.index(args[0],len(value._items),end=operation=='insert');incoming=args[1]
            old=value._items[index] if operation=='set' else None
            if operation!='set':
                cap=min(shared.values.MAX_LIST,prop._upper if prop._upper>=0 else shared.values.MAX_LIST)
                if len(value._items)>=cap:raise ValueError('XDTO: превышен размер списка')
            nodes,units=_input(boundary,parent,prop,incoming,old,operation=='set')
            if operation!='set':nodes+=1
            changed.extend((old,incoming if type(incoming) is _OBJECT else None))
        elif operation=='delete':
            index=len(value._items)-1 if not args else shared.values.index(args[0],len(value._items))
            if index<0:raise ValueError('XDTO: список пуст')
            changed.append(value._items[index])
        elif operation=='clear':changed.extend(value._items)
        elif operation in ('get','get_xdto'):
            if not(type(args[0]) is int or type(args[0]) is Decimal):raise ValueError('source XDTO index requires Number')
        _budget(factory,nodes,units)
        result=method(value,*args)
        if operation in _MUTATIONS:
            if type(result) is shared._VALUE or type(result) is _OBJECT:changed.append(result)
            _publish(boundary,owner,factory,*changed)
        _check(boundary,value);return result
    if allow_references:call.requires_reference=lambda index:False
    return call


def captured(boundary,function,**contract):
    if type(function) is not HostFunction:return None
    from .python_direct_source_xdto_local import _host_hooks
    _host_hooks()
    _fields(function)
    callback=function.function
    if type(callback) is not MethodType or not owns(callback.__self__):return None
    value=callback.__self__
    candidates=((_UNSET,(1,),False,'unset'),) if type(value) is _OBJECT else tuple(_METHODS.values())
    match=next((item for item in candidates if item[0] is callback.__func__),None)
    if match is None:raise BoundaryViolation('source XDTO saved method changed')
    def validate():
        _fields(function)
        if function.function is not callback or function.returns_value is not match[2] or type(function.reference_parameters) is not frozenset or function.reference_parameters:
            raise BoundaryViolation('source XDTO saved method contract changed')
    return resolve(boundary,value,"getxdto" if match[3]=="get_xdto" else match[3],validate=validate,**contract)


def iterate(boundary,value):
    _check(boundary,value)
    if type(value) is not _LIST:raise ValueError('source XDTO object is not iterable')
    for child in tuple(value._items):
        _check(boundary,value);yield _native(child)
